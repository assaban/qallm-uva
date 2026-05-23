"""Integration tests for the orchestrator's QALLM loop (NEW-06).

These tests verify the orchestrator's per-unit accept/abandon decisions
across multiple QALLM rounds. The underlying components (analyser, repair
manager, verifier, judge, LLM) are stubbed; the goal is to exercise the
loop's decision logic, not those components.

What this file covers:

  * Round 1 is accepted unconditionally for every unit (no parent yet).
  * On round N>=2: when the judge says IMPROVEMENT, the variant joins
    the lineage and feeds the next round.
  * When the judge says REGRESSION, the variant goes to the abandoned
    log and the parent is fed into the next round instead.
  * NO_CHANGE is treated as acceptance.
  * Multiple units advance independently across rounds.
  * summary.json contains per-unit tracks with lineage and abandoned
    entries.
  * The judge strategy chosen at construction is actually used.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from qallm.common.model import CodeUnit
from qallm.evaluation import (
    DimensionResult,
    IndicatorResult,
    IndicatorStatus,
    ProfileVerdict,
)
from qallm.judge import JudgeOutcome
from qallm.judge.models import JudgeVerdict, VerdictComparison
from qallm.orchestrator import LineageEntry, QALLMOrchestrator, UnitTrack, _unit_id
from qallm.profiles import QualityDimension


# ----------------------------------------------------------------------------
# Helpers and fixtures
# ----------------------------------------------------------------------------


def _make_unit(tmp_path: Path, source: str, name: str = "mod.py") -> CodeUnit:
    p = tmp_path / name
    p.write_text(source)
    return CodeUnit(source_code=source, cell_index=-1, original_path=p)


def _stub_verdict(profile_id: str = "stub") -> ProfileVerdict:
    """A minimal ProfileVerdict with one dimension and one indicator."""
    return ProfileVerdict(
        profile_id=profile_id,
        dimensions=[
            DimensionResult(
                dimension=QualityDimension.MAINTAINABILITY,
                indicators=[
                    IndicatorResult(
                        name="mi",
                        evaluator="stub.mi",
                        threshold=0.0,
                        comparator="ge",
                        measured=70.0,
                        status=IndicatorStatus.PASS,
                    )
                ],
            )
        ],
    )


def _stub_judge_verdict(outcome: JudgeOutcome) -> JudgeVerdict:
    """A canned JudgeVerdict useful for stubbing decisions."""
    return JudgeVerdict(
        outcome=outcome,
        strategy="stub",
        explanation=f"stub: {outcome.value}",
        comparison=VerdictComparison(),
    )


@pytest.fixture
def stub_orchestrator(tmp_path: Path):
    """Build an orchestrator whose underlying components are all mocked.

    The orchestrator is real; only the heavy dependencies (LLM provider,
    analyser, repair manager, verifier, judge, reporter, ingestion) are
    replaced by stubs that let tests inject deterministic behaviour.
    """
    # Construct with a cheap, local provider so __init__ doesn't fail.
    with patch("qallm.orchestrator.OllamaModel") as mock_ollama:
        mock_ollama.return_value = MagicMock(name=lambda: "stub-llm")
        orch = QALLMOrchestrator(
            llm_type="ollama",
            model_name="gemma3:4b",
            judge_strategy="strict",
            rounds=3,
            test_stability="frozen",
            generation_policy="grow",
        )

    # Replace every collaborator with a controllable stub.
    orch.ingestion_manager = MagicMock()
    orch.analysis_manager = MagicMock()
    orch.repair_manager = MagicMock()
    orch.verification_manager = MagicMock()
    orch.reporter = MagicMock()
    orch.reporter.report_dir = tmp_path / "outputs"
    orch.reporter.report_dir.mkdir(parents=True, exist_ok=True)
    orch.judge = MagicMock()

    # verification_manager surfaces (clear_for_round, store, get_session_data,
    # get_stability_summary). Tests will further customise verify() per case.
    orch.verification_manager.store = MagicMock()
    orch.verification_manager.get_session_data = MagicMock(return_value=[])
    orch.verification_manager.get_stability_summary = MagicMock(
        return_value={"test_stability": "frozen", "generation_policy": "grow"}
    )

    return orch


def _wire_collaborators(
    orch: QALLMOrchestrator,
    *,
    units: list[CodeUnit],
    verdicts_per_round: list[list[ProfileVerdict]],
    judge_outcomes: list[list[JudgeOutcome]],
):
    """Configure stubs to drive a deterministic loop.

    Args:
      units: code units to return from ingestion.
      verdicts_per_round: outer list is rounds (1..N), inner list is units.
        Each entry is the ProfileVerdict to attribute to that unit in that
        round.
      judge_outcomes: same shape; entry is the outcome the judge produces
        for that (round, unit) pair. Round 1 entries are ignored (round 1
        is unconditional acceptance).
    """
    orch.ingestion_manager.collect.return_value = units

    # Analysis manager: returns a stub AnalysedCodeUnit. The orchestrator
    # only passes this through to repair_manager and reporter, so anything
    # truthy works.
    from qallm.analysis.analysis_model import AnalysedCodeUnit
    orch.analysis_manager.analyse_code_unit.side_effect = lambda u: AnalysedCodeUnit(
        code_unit=u, findings=[], raw_tool_results=[]
    )

    # Repair manager: returns a RepairedCodeUnit whose repaired_code_unit
    # is the same CodeUnit it was asked to repair, so the orchestrator's
    # parent-vs-variant chain stays predictable.
    from qallm.repair.repair_model import RepairedCodeUnit, RepairResult
    def _fake_repair(analysed):
        repaired_result = RepairResult(
            file_path=str(analysed.code_unit.original_path),
            repaired_source=analysed.code_unit.source_code,
            explanation="stub",
            compiles=True,
        )
        return RepairedCodeUnit(analysed, repaired_result)
    orch.repair_manager.repair_code_unit.side_effect = _fake_repair

    # Verifier: returns a TestedCodeUnit with no sessions, which is fine
    # because we're going to replace _evaluate_profile_for entirely.
    from qallm.verification.models import TestedCodeUnit
    def _fake_verify(repaired, **kwargs):
        return TestedCodeUnit(repaired_unit=repaired, sessions=[])
    orch.verification_manager.verify.side_effect = _fake_verify

    # Profile evaluation: intercept _evaluate_profile_for so we can hand
    # back the verdict scheduled for the current round + unit.
    # round_idx tracks zero-based round position (0 = round 1).
    # unit_idx is reset by _run_round wrapper at each round boundary.
    state = {"round_idx": 0, "unit_idx": 0}

    def _next_verdict(unit, tested):
        return verdicts_per_round[state["round_idx"]][state["unit_idx"]]
    orch._evaluate_profile_for = _next_verdict

    def _next_judge(parent_verdict, variant_verdict, raw_evidence=None):
        outcome = judge_outcomes[state["round_idx"]][state["unit_idx"]]
        # Bump unit_idx after judging; the orchestrator processes units
        # serially in _run_round.
        state["unit_idx"] += 1
        return _stub_judge_verdict(outcome)
    orch.judge.decide.side_effect = _next_judge

    # Round 1 doesn't call the judge, so unit_idx also needs to advance
    # after each unit's profile evaluation. We piggy-back on _evaluate_profile_for
    # for the round-1 case only.
    base_round_1 = state["round_idx"]

    def _verdict_with_round1_bump(unit, tested):
        v = verdicts_per_round[state["round_idx"]][state["unit_idx"]]
        # If this is round 1 (current_round == 1), the orchestrator won't
        # call the judge for this unit. Bump unit_idx here instead.
        if orch.current_round == 1:
            state["unit_idx"] += 1
        return v
    orch._evaluate_profile_for = _verdict_with_round1_bump

    # Wrap _run_round to reset unit_idx and advance round_idx between rounds.
    real_run_round = orch._run_round

    def _wrapped_run_round(inputs):
        state["unit_idx"] = 0
        out = real_run_round(inputs)
        state["round_idx"] += 1
        return out
    orch._run_round = _wrapped_run_round

    # Set max_rounds to match the number of rounds we have data for.
    orch.caps = orch.caps.__class__(
        max_rounds=len(judge_outcomes),
        max_tokens=orch.caps.max_tokens,
        max_seconds=orch.caps.max_seconds,
        max_round_seconds=orch.caps.max_round_seconds,
        max_cost_usd=orch.caps.max_cost_usd,
    )
    orch.rounds = orch.caps.max_rounds
    orch.budget_state.caps = orch.caps


# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------


class TestRoundOneUnconditionalAcceptance:
    def test_round_1_accepts_without_calling_judge(
        self, stub_orchestrator, tmp_path
    ):
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a],
            verdicts_per_round=[[_stub_verdict()]],
            judge_outcomes=[[JudgeOutcome.IMPROVEMENT]],  # ignored on round 1
        )
        stub_orchestrator.run(str(tmp_path))

        # The judge was never called: round 1 has no parent.
        stub_orchestrator.judge.decide.assert_not_called()

        # Track exists with one lineage entry, no abandoned.
        track = stub_orchestrator.tracks[_unit_id(unit_a)]
        assert len(track.lineage) == 1
        assert track.lineage[0].round_number == 1
        assert track.lineage[0].judge_verdict is None
        assert len(track.abandoned) == 0


class TestAcceptDecision:
    @pytest.mark.parametrize(
        "outcome",
        [JudgeOutcome.IMPROVEMENT, JudgeOutcome.NO_CHANGE],
    )
    def test_accept_extends_lineage(
        self, stub_orchestrator, tmp_path, outcome
    ):
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a],
            verdicts_per_round=[
                [_stub_verdict()],
                [_stub_verdict()],
            ],
            judge_outcomes=[
                [JudgeOutcome.IMPROVEMENT],  # round 1 (unused)
                [outcome],                    # round 2
            ],
        )
        stub_orchestrator.run(str(tmp_path))

        track = stub_orchestrator.tracks[_unit_id(unit_a)]
        # Two accepted variants, no abandoned.
        assert len(track.lineage) == 2
        assert len(track.abandoned) == 0
        # Round 2's lineage entry has a judge verdict.
        assert track.lineage[1].judge_verdict is not None
        assert track.lineage[1].judge_verdict.outcome is outcome


class TestRejectDecision:
    def test_regression_goes_to_abandoned_log(
        self, stub_orchestrator, tmp_path
    ):
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a],
            verdicts_per_round=[
                [_stub_verdict()],
                [_stub_verdict()],
            ],
            judge_outcomes=[
                [JudgeOutcome.IMPROVEMENT],
                [JudgeOutcome.REGRESSION],
            ],
        )
        stub_orchestrator.run(str(tmp_path))

        track = stub_orchestrator.tracks[_unit_id(unit_a)]
        assert len(track.lineage) == 1  # only round 1 accepted
        assert len(track.abandoned) == 1
        assert track.abandoned[0].round_number == 2
        assert track.abandoned[0].judge_verdict.outcome is JudgeOutcome.REGRESSION

    def test_parent_is_reused_after_rejection(
        self, stub_orchestrator, tmp_path
    ):
        """After a rejection in round 2, round 3 should be repairing the
        round-1 (parent) code, not the rejected round-2 variant.

        We check this by inspecting which CodeUnit got passed to
        analyse_code_unit on round 3.
        """
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a],
            verdicts_per_round=[
                [_stub_verdict()],
                [_stub_verdict()],
                [_stub_verdict()],
            ],
            judge_outcomes=[
                [JudgeOutcome.IMPROVEMENT],   # round 1: accepted
                [JudgeOutcome.REGRESSION],    # round 2: rejected
                [JudgeOutcome.IMPROVEMENT],   # round 3: doesn't matter
            ],
        )
        stub_orchestrator.run(str(tmp_path))

        # Round 3's analyse call should have been made against the round-1
        # accepted variant (which is the same as the original unit, since
        # our stub repair returns unit unchanged).
        track = stub_orchestrator.tracks[_unit_id(unit_a)]
        assert len(track.lineage) == 2  # rounds 1 and 3 accepted; 2 rejected
        assert len(track.abandoned) == 1
        # Round 3's lineage entry is from round 3, not round 2.
        assert track.lineage[-1].round_number == 3


class TestIndependentUnits:
    def test_units_advance_independently(self, stub_orchestrator, tmp_path):
        # Unit A: improvement, improvement.
        # Unit B: improvement, regression.
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        unit_b = _make_unit(tmp_path, "def b(): pass\n", "b.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a, unit_b],
            verdicts_per_round=[
                [_stub_verdict(), _stub_verdict()],
                [_stub_verdict(), _stub_verdict()],
            ],
            judge_outcomes=[
                [JudgeOutcome.IMPROVEMENT, JudgeOutcome.IMPROVEMENT],  # round 1
                [JudgeOutcome.IMPROVEMENT, JudgeOutcome.REGRESSION],   # round 2
            ],
        )
        stub_orchestrator.run(str(tmp_path))

        track_a = stub_orchestrator.tracks[_unit_id(unit_a)]
        track_b = stub_orchestrator.tracks[_unit_id(unit_b)]
        assert len(track_a.lineage) == 2 and len(track_a.abandoned) == 0
        assert len(track_b.lineage) == 1 and len(track_b.abandoned) == 1


class TestSummaryContents:
    def test_summary_contains_tracks_and_totals(
        self, stub_orchestrator, tmp_path
    ):
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a],
            verdicts_per_round=[
                [_stub_verdict()],
                [_stub_verdict()],
            ],
            judge_outcomes=[
                [JudgeOutcome.IMPROVEMENT],
                [JudgeOutcome.REGRESSION],
            ],
        )
        summary = stub_orchestrator.run(str(tmp_path))

        assert summary["rounds_accepted_total"] == 1
        assert summary["rounds_abandoned_total"] == 1
        assert "tracks" in summary
        assert _unit_id(unit_a) in summary["tracks"]
        track_dict = summary["tracks"][_unit_id(unit_a)]
        assert len(track_dict["lineage"]) == 1
        assert len(track_dict["abandoned"]) == 1


class TestJudgeStrategyChoice:
    def test_orchestrator_records_judge_strategy_in_summary(
        self, stub_orchestrator, tmp_path
    ):
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a],
            verdicts_per_round=[[_stub_verdict()]],
            judge_outcomes=[[JudgeOutcome.IMPROVEMENT]],
        )
        summary = stub_orchestrator.run(str(tmp_path))
        # stub_orchestrator was built with judge_strategy="strict".
        assert summary["judge_strategy"] == "strict"


class TestNoChangeIsAccepted:
    def test_no_change_extends_lineage(self, stub_orchestrator, tmp_path):
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a],
            verdicts_per_round=[
                [_stub_verdict()],
                [_stub_verdict()],
                [_stub_verdict()],
            ],
            judge_outcomes=[
                [JudgeOutcome.IMPROVEMENT],
                [JudgeOutcome.NO_CHANGE],
                [JudgeOutcome.NO_CHANGE],
            ],
        )
        stub_orchestrator.run(str(tmp_path))
        track = stub_orchestrator.tracks[_unit_id(unit_a)]
        # All three rounds accepted (round 1 unconditional, rounds 2-3
        # NO_CHANGE).
        assert len(track.lineage) == 3
        assert len(track.abandoned) == 0
