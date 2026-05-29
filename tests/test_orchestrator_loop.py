"""Integration tests for the orchestrator's QALLM loop.

These tests verify the orchestrator's per-unit accept/abandon decisions
across multiple QALLM rounds. The underlying components (analyser, repair
manager, verifier, judge, LLM) are stubbed; the goal is to exercise the
loop's decision logic, not those components.

What this file covers:

  * Round 0 (baseline) is recorded on the lineage with a ProfileVerdict
    but no judge verdict (it has no parent to compare against).
  * Round 1 is judged against the round-0 baseline. There is no longer
    an "unconditionally accepted first round" case.
  * On any repair round N>=1: when the judge says IMPROVEMENT or
    NO_CHANGE, the variant joins the lineage and feeds the next round.
  * When the judge says REGRESSION, the variant goes to the abandoned
    log and the parent is fed into the next round instead.
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
    baseline_verdicts: list[ProfileVerdict] | None = None,
    repair_verdicts: list[list[ProfileVerdict]],
    judge_outcomes: list[list[JudgeOutcome]],
):
    """Configure stubs to drive a deterministic loop.

    Args:
      units: code units to return from ingestion.
      baseline_verdicts: ProfileVerdict per unit for round 0. If omitted,
        a fresh ``_stub_verdict()`` is used for each unit. The orchestrator
        calls ``_evaluate_profile_for`` once per unit in round 0.
      repair_verdicts: outer list is repair rounds (1..N), inner list is
        units. Each entry is the ProfileVerdict to attribute to that unit
        in that repair round.
      judge_outcomes: same shape as ``repair_verdicts``. Entry is the
        outcome the judge produces for that (round, unit) pair. Every
        repair round (including round 1) calls the judge against the
        parent (round 0 baseline for round 1).
    """
    orch.ingestion_manager.collect.return_value = units

    # Default baseline verdicts: one fresh stub per unit.
    if baseline_verdicts is None:
        baseline_verdicts = [_stub_verdict() for _ in units]
    assert len(baseline_verdicts) == len(units), (
        f"baseline_verdicts must have one entry per unit "
        f"({len(units)}), got {len(baseline_verdicts)}"
    )

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
    #
    # Round 0 (baseline): orchestrator calls _evaluate_profile_for once
    # per unit, in order. We consume baseline_verdicts sequentially.
    # Rounds 1..N (repair): orchestrator calls _evaluate_profile_for
    # once per unit per round, indexed by (repair_round_idx, unit_idx).
    state = {"baseline_idx": 0, "repair_round_idx": 0, "unit_idx": 0}

    def _next_verdict(unit, tested):
        if orch.current_round == 0:
            v = baseline_verdicts[state["baseline_idx"]]
            state["baseline_idx"] += 1
            return v
        return repair_verdicts[state["repair_round_idx"]][state["unit_idx"]]
    orch._evaluate_profile_for = _next_verdict

    def _next_judge(parent_verdict, variant_verdict, raw_evidence=None):
        # Judge is only called in repair rounds (1..N), never in round 0.
        outcome = judge_outcomes[state["repair_round_idx"]][state["unit_idx"]]
        # Bump unit_idx after judging; the orchestrator processes units
        # serially within a round.
        state["unit_idx"] += 1
        return _stub_judge_verdict(outcome)
    orch.judge.decide.side_effect = _next_judge

    # Wrap _run_round to reset unit_idx between rounds and advance
    # repair_round_idx between *repair* rounds. The baseline (round 0) now
    # flows through _run_round too (the unified _process_unit path), so we
    # must not treat it as a repair round: reset unit_idx for every round,
    # but only advance repair_round_idx once we are past the baseline.
    real_run_round = orch._run_round

    def _wrapped_run_round(inputs):
        state["unit_idx"] = 0
        is_baseline = orch.current_round == 0
        out = real_run_round(inputs)
        if not is_baseline:
            state["repair_round_idx"] += 1
        return out
    orch._run_round = _wrapped_run_round

    # Set max_rounds to match the number of repair rounds we have data for.
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


class TestBaselineAndFirstRound:
    """Round 0 is recorded on the lineage; round 1 is judged against it."""

    def test_round_0_records_baseline_without_calling_judge(
        self, stub_orchestrator, tmp_path
    ):
        """The baseline (round 0) is the only round in the run with no
        judge verdict. Every subsequent round including round 1 is
        judged against its parent.
        """
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a],
            repair_verdicts=[[_stub_verdict()]],
            judge_outcomes=[[JudgeOutcome.IMPROVEMENT]],  # round 1
        )
        stub_orchestrator.run(str(tmp_path))

        # Judge was called once: for round 1 against round 0.
        assert stub_orchestrator.judge.decide.call_count == 1

        track = stub_orchestrator.tracks[_unit_id(unit_a)]
        # Two lineage entries: round 0 baseline, round 1 accepted.
        assert len(track.lineage) == 2
        # Round 0: no judge verdict; round 1: judged.
        assert track.lineage[0].round_number == 0
        assert track.lineage[0].judge_verdict is None
        assert track.lineage[1].round_number == 1
        assert track.lineage[1].judge_verdict is not None
        assert len(track.abandoned) == 0

    def test_round_1_can_be_abandoned(self, stub_orchestrator, tmp_path):
        """Now that round 1 is judged, it can also be abandoned.

        This is the methodological reason the change was made: when round
        1's repair regresses against the original baseline, it should not
        be accepted just because it's the first repair.
        """
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a],
            repair_verdicts=[[_stub_verdict()]],
            judge_outcomes=[[JudgeOutcome.REGRESSION]],  # round 1 regresses
        )
        stub_orchestrator.run(str(tmp_path))

        track = stub_orchestrator.tracks[_unit_id(unit_a)]
        # Only the baseline remains on the lineage; round 1 was abandoned.
        assert len(track.lineage) == 1
        assert track.lineage[0].round_number == 0
        assert len(track.abandoned) == 1
        assert track.abandoned[0].round_number == 1
        assert track.abandoned[0].judge_verdict.outcome is JudgeOutcome.REGRESSION

    def test_baseline_verify_runs_against_original_source(
        self, stub_orchestrator, tmp_path
    ):
        """Verify the baseline calls verification_manager.verify with a
        synthetic RepairedCodeUnit whose repaired source equals the
        original (no repair has happened yet at round 0).

        This is the integrity check for the methodology claim: the
        "verification gap" is measured against the original code, not
        against a repair of it.
        """
        original_source = "def needs_testing(x): return x * 2\n"
        unit_a = _make_unit(tmp_path, original_source, "a.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a],
            repair_verdicts=[[_stub_verdict()]],
            judge_outcomes=[[JudgeOutcome.IMPROVEMENT]],
        )
        stub_orchestrator.run(str(tmp_path))

        # verify was called at least twice: once for baseline, once for
        # round 1. Inspect the FIRST call: that's the baseline.
        verify_calls = stub_orchestrator.verification_manager.verify.call_args_list
        assert len(verify_calls) >= 2

        baseline_call = verify_calls[0]
        baseline_repaired = baseline_call.args[0]
        # The synthetic baseline RepairedCodeUnit has the original source
        # on both sides; no actual repair was applied.
        assert baseline_repaired.repaired_code_unit.source_code == original_source
        assert baseline_repaired.original_code_unit.source_code == original_source
        # And it was tagged as round 0 so the stability store treats it
        # as the baseline test-generation round.
        assert baseline_call.kwargs["round_number"] == 0

        # Sanity: repair_manager was NOT called for the baseline. It was
        # called once for round 1.
        assert stub_orchestrator.repair_manager.repair_code_unit.call_count == 1


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
            repair_verdicts=[
                [_stub_verdict()],  # round 1
                [_stub_verdict()],  # round 2
            ],
            judge_outcomes=[
                [JudgeOutcome.IMPROVEMENT],   # round 1
                [outcome],                     # round 2
            ],
        )
        stub_orchestrator.run(str(tmp_path))

        track = stub_orchestrator.tracks[_unit_id(unit_a)]
        # Three lineage entries: round 0 baseline + rounds 1, 2 accepted.
        assert len(track.lineage) == 3
        assert track.lineage[0].round_number == 0
        assert track.lineage[1].round_number == 1
        assert track.lineage[2].round_number == 2
        assert len(track.abandoned) == 0
        # Round 2's lineage entry has the expected judge verdict.
        assert track.lineage[2].judge_verdict is not None
        assert track.lineage[2].judge_verdict.outcome is outcome


class TestRejectDecision:
    def test_regression_goes_to_abandoned_log(
        self, stub_orchestrator, tmp_path
    ):
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a],
            repair_verdicts=[
                [_stub_verdict()],  # round 1
                [_stub_verdict()],  # round 2
            ],
            judge_outcomes=[
                [JudgeOutcome.IMPROVEMENT],   # round 1: accepted
                [JudgeOutcome.REGRESSION],    # round 2: rejected
            ],
        )
        stub_orchestrator.run(str(tmp_path))

        track = stub_orchestrator.tracks[_unit_id(unit_a)]
        # Lineage: round 0 baseline + round 1 accepted.
        assert len(track.lineage) == 2
        assert track.lineage[0].round_number == 0
        assert track.lineage[1].round_number == 1
        # Abandoned: round 2.
        assert len(track.abandoned) == 1
        assert track.abandoned[0].round_number == 2
        assert track.abandoned[0].judge_verdict.outcome is JudgeOutcome.REGRESSION

    def test_parent_is_reused_after_rejection(
        self, stub_orchestrator, tmp_path
    ):
        """After a rejection in round 2, round 3 should be repairing the
        round-1 accepted variant, not the rejected round-2 variant.
        """
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a],
            repair_verdicts=[
                [_stub_verdict()],  # round 1
                [_stub_verdict()],  # round 2
                [_stub_verdict()],  # round 3
            ],
            judge_outcomes=[
                [JudgeOutcome.IMPROVEMENT],   # round 1: accepted
                [JudgeOutcome.REGRESSION],    # round 2: rejected
                [JudgeOutcome.IMPROVEMENT],   # round 3: accepted
            ],
        )
        stub_orchestrator.run(str(tmp_path))

        track = stub_orchestrator.tracks[_unit_id(unit_a)]
        # Lineage: round 0 baseline + rounds 1, 3 accepted.
        assert len(track.lineage) == 3
        assert [e.round_number for e in track.lineage] == [0, 1, 3]
        # Abandoned: round 2.
        assert len(track.abandoned) == 1
        assert track.abandoned[0].round_number == 2


class TestIndependentUnits:
    def test_units_advance_independently(self, stub_orchestrator, tmp_path):
        # Unit A: improvement, improvement.
        # Unit B: improvement, regression.
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        unit_b = _make_unit(tmp_path, "def b(): pass\n", "b.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a, unit_b],
            repair_verdicts=[
                [_stub_verdict(), _stub_verdict()],  # round 1
                [_stub_verdict(), _stub_verdict()],  # round 2
            ],
            judge_outcomes=[
                [JudgeOutcome.IMPROVEMENT, JudgeOutcome.IMPROVEMENT],  # round 1
                [JudgeOutcome.IMPROVEMENT, JudgeOutcome.REGRESSION],   # round 2
            ],
        )
        stub_orchestrator.run(str(tmp_path))

        track_a = stub_orchestrator.tracks[_unit_id(unit_a)]
        track_b = stub_orchestrator.tracks[_unit_id(unit_b)]
        # Unit A: baseline + round 1 + round 2 accepted = 3 lineage entries.
        assert len(track_a.lineage) == 3 and len(track_a.abandoned) == 0
        # Unit B: baseline + round 1 accepted; round 2 abandoned.
        assert len(track_b.lineage) == 2 and len(track_b.abandoned) == 1


class TestSummaryContents:
    def test_summary_contains_tracks_and_totals(
        self, stub_orchestrator, tmp_path
    ):
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a],
            repair_verdicts=[
                [_stub_verdict()],  # round 1
                [_stub_verdict()],  # round 2
            ],
            judge_outcomes=[
                [JudgeOutcome.IMPROVEMENT],   # round 1
                [JudgeOutcome.REGRESSION],    # round 2
            ],
        )
        summary = stub_orchestrator.run(str(tmp_path))

        # Lineage entries: round 0 baseline + round 1 accepted = 2.
        # Abandoned entries: round 2 = 1.
        assert summary["rounds_accepted_total"] == 2
        assert summary["rounds_abandoned_total"] == 1
        assert "tracks" in summary
        assert _unit_id(unit_a) in summary["tracks"]
        track_dict = summary["tracks"][_unit_id(unit_a)]
        assert len(track_dict["lineage"]) == 2
        assert len(track_dict["abandoned"]) == 1


class TestJudgeStrategyChoice:
    def test_orchestrator_records_judge_strategy_in_summary(
        self, stub_orchestrator, tmp_path
    ):
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a],
            repair_verdicts=[[_stub_verdict()]],
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
            repair_verdicts=[
                [_stub_verdict()],  # round 1
                [_stub_verdict()],  # round 2
                [_stub_verdict()],  # round 3
            ],
            judge_outcomes=[
                [JudgeOutcome.IMPROVEMENT],
                [JudgeOutcome.NO_CHANGE],
                [JudgeOutcome.NO_CHANGE],
            ],
        )
        stub_orchestrator.run(str(tmp_path))
        track = stub_orchestrator.tracks[_unit_id(unit_a)]
        # Four lineage entries: round 0 baseline + rounds 1, 2, 3 accepted.
        assert len(track.lineage) == 4
        assert [e.round_number for e in track.lineage] == [0, 1, 2, 3]
        assert len(track.abandoned) == 0


class TestReporterIntegration:
    """Assert the orchestrator drives the v3 reporter API.

    Post baseline-verification change: ``save_round_artefacts`` is now
    called once per unit for the baseline (round 0) AND once per unit
    per repair round. The legacy ``save_baseline`` is no longer invoked
    by ``run()``.
    """

    def test_save_round_artefacts_called_for_baseline(
        self, stub_orchestrator, tmp_path
    ):
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        unit_b = _make_unit(tmp_path, "def b(): pass\n", "b.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a, unit_b],
            repair_verdicts=[[_stub_verdict(), _stub_verdict()]],
            judge_outcomes=[[JudgeOutcome.IMPROVEMENT, JudgeOutcome.IMPROVEMENT]],
        )
        stub_orchestrator.run(str(tmp_path))
        # 2 units × (1 baseline + 1 repair round) = 4 save calls.
        calls = stub_orchestrator.reporter.save_round_artefacts.call_args_list
        assert len(calls) == 4
        # First two calls are baseline (round_number=0) and accepted.
        baseline_calls = [c for c in calls if c.kwargs["round_number"] == 0]
        assert len(baseline_calls) == 2
        for c in baseline_calls:
            assert c.kwargs["accepted"] is True
            assert c.kwargs["judge_verdict_dict"] is None

    def test_save_round_artefacts_routes_accepted_into_lineage(
        self, stub_orchestrator, tmp_path
    ):
        unit_a = _make_unit(tmp_path, "def a(): pass\n", "a.py")
        _wire_collaborators(
            stub_orchestrator,
            units=[unit_a],
            repair_verdicts=[
                [_stub_verdict()],  # round 1
                [_stub_verdict()],  # round 2
            ],
            judge_outcomes=[
                [JudgeOutcome.IMPROVEMENT],   # round 1: accepted
                [JudgeOutcome.REGRESSION],    # round 2: abandoned
            ],
        )
        stub_orchestrator.run(str(tmp_path))
        # Three save_round_artefacts calls total: baseline + round 1 + round 2.
        calls = stub_orchestrator.reporter.save_round_artefacts.call_args_list
        assert len(calls) == 3
        # Order: round 0 (accepted), round 1 (accepted), round 2 (abandoned).
        assert calls[0].kwargs["round_number"] == 0
        assert calls[0].kwargs["accepted"] is True
        assert calls[1].kwargs["round_number"] == 1
        assert calls[1].kwargs["accepted"] is True
        assert calls[2].kwargs["round_number"] == 2
        assert calls[2].kwargs["accepted"] is False