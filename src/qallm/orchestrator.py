"""QALLM Orchestrator: the main pipeline conductor.

Per workflow design v3 sections 3, 5, and 9.3. The orchestrator runs
QALLM rounds and decides per code unit whether each round's variant is
accepted or abandoned.

Loop shape
----------

.. code-block:: text

    Round 0 (Baseline):    Analyse + verify the original code unit.
                           No repair. Produces a ProfileVerdict that
                           becomes the first lineage entry. This is the
                           ground truth against which round 1 is judged.
    Round 1..N:
      for each code unit:
        1. Analyse current variant (or unit if round 1).
        2. Repair based on analysis.
        3. Verify (generate or replay tests; record session).
        4. Build a ProfileVerdict for the variant.
        5. Judge variant vs parent (the last accepted variant for this
           unit; for round 1 the parent is the round 0 baseline).
        6. If IMPROVEMENT or NO_CHANGE: variant becomes parent of next round.
           If REGRESSION: variant is logged as abandoned; parent stays.

A unit's "lineage" is the chain of accepted variants, starting with the
round 0 baseline. A unit's "abandoned" list grows with each rejected
variant. Every round including round 1 is judged against its parent;
round 0 itself has no judge verdict (no parent to compare against).

Methodology rationale
---------------------
Running verification on the original code at round 0 makes the
"verification gap" claim measurable: of the units that pass static
analysis, how many had a runtime defect detectable by execution-based
testing? Without round 0 verification, that question can only be
answered against the *first repair* of the code, not the original. See
docs/workflow-design.md section 4 and docs/methodology-decisions.md
for the full rationale.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
import json
import logging
from dataclasses import dataclass, field
from typing import Literal, Optional

from qallm.analysis.normalizer import LifecycleStage
from qallm.config import settings
from qallm.ingestion.ingestion_manager import IngestionManager
from qallm.common.model import CodeUnit
from qallm.cost import BudgetCaps, BudgetState, HaltReason
from qallm.evaluation import ProfileVerdict, evaluate_profile
from qallm.improvement import build_improvement_report
from qallm.judge import (
    JudgeOutcome,
    JudgeStrategy,
    JudgeVerdict,
    build_judge,
)
from qallm.llm.anthropic_provider import AnthropicModel
from qallm.llm.base import LLMModel, TokenTracker
from qallm.llm.ollama_provider import OllamaModel
from qallm.llm.openai_provider import OpenAIModel
from qallm.llm.transcript import (
    TranscriptRecorder,
    active_recorder,
    reset_context,
    set_context,
)
from qallm.profiles import IMPLEMENTATION_DEFAULT, QualityProfile
from qallm.utils.reporter import QualityReporter
from qallm.verification.models import OracleType, TestedCodeUnit
from qallm.verification.test_persistence import TestStabilityConfig
from qallm.verification.verification_manager import VerificationManager
from qallm.analysis.analysis_manager import AnalysisManager
from qallm.repair.repair_manager import RepairManager
from qallm.repair.repair_model import RepairedCodeUnit, RepairResult
from qallm.repair.agents.llm_repair_agent import LLMRepairAgent

logger = logging.getLogger(__name__)

Strategy = Literal["feedback", "rl", "oneshot", "hypothesis"]
# ``feedback`` is the canonical name for the iterative-feedback verifier
# (the proposed method). ``rl`` is retained as a back-compat alias and is
# normalised to ``feedback`` semantics at assignment; both select the same
# multi-round, execution-feedback verification path.

LLM_PROVIDERS = {
    "ollama": OllamaModel,
    "openai": OpenAIModel,
    "anthropic": AnthropicModel,
}


@dataclass
class LineageEntry:
    """One accepted variant in a code unit's lineage."""

    round_number: int
    code_unit: CodeUnit
    verdict: ProfileVerdict
    judge_verdict: Optional[JudgeVerdict] = None  # None for round 0 baseline only

    def to_dict(self) -> dict:
        return {
            "round_number": self.round_number,
            "verdict": self.verdict.to_dict(),
            "judge_verdict": (
                self.judge_verdict.to_dict() if self.judge_verdict else None
            ),
        }


@dataclass
class AbandonedEntry:
    """One rejected variant, kept for the abandoned log."""

    round_number: int
    code_unit: CodeUnit
    verdict: ProfileVerdict
    judge_verdict: JudgeVerdict

    def to_dict(self) -> dict:
        return {
            "round_number": self.round_number,
            "verdict": self.verdict.to_dict(),
            "judge_verdict": self.judge_verdict.to_dict(),
        }


@dataclass
class UnitTrack:
    """Per-unit state across QALLM rounds.

    Each code unit has its own lineage (chain of accepted variants) and
    abandoned list (rejected variants). The unit's *parent* for the next
    round is always the last entry in lineage.
    """

    unit_id: str  # stable identifier: f"{path}::{cell_index}"
    lineage: list[LineageEntry] = field(default_factory=list)
    abandoned: list[AbandonedEntry] = field(default_factory=list)

    @property
    def current_parent(self) -> Optional[LineageEntry]:
        return self.lineage[-1] if self.lineage else None

    @property
    def current_code_unit(self) -> Optional[CodeUnit]:
        parent = self.current_parent
        return parent.code_unit if parent else None

    def to_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "lineage": [e.to_dict() for e in self.lineage],
            "abandoned": [e.to_dict() for e in self.abandoned],
        }


@dataclass
class OrchestratorProgress:
    """A snapshot of orchestrator progress, safe to expose via the API.

    The orchestrator updates a handful of public attributes as it works
    (``current_phase``, ``current_stage``, ``current_unit_id``). The
    ``snapshot()`` method on the orchestrator reads those plus other
    durable state (tracks, budget, halt reason) and returns this dataclass.

    Designed for *display*, not for *control*. The fields are descriptive
    strings and counts. The UI renders them as a status line plus live
    counters; it does not infer a percentage.

    Why "snapshot": the orchestrator is running in a worker thread when
    the API endpoint reads its state. We never block on the worker, never
    take a lock. Python's GIL plus the fact that we only *read* primitive
    attributes makes a moment-in-time snapshot safe. The user does not
    care if the values are 50 milliseconds old.
    """

    # Top-level phase.
    phase: Literal["initialising", "baseline", "rounds", "summary", "done"]
    # Within the rounds phase.
    current_round: int
    total_rounds: int
    # Within one round, the stage of work for the *current* unit.
    current_stage: Optional[Literal["analyse", "repair", "verify", "judge"]]
    current_unit_id: Optional[str]
    # Within the verify stage, the function currently being verified.
    # On slow local LLMs an 8-function unit can spend 10+ minutes in
    # verify; without function-level progress the user sees no change
    # for that whole window.
    current_function: Optional[str]
    function_index: int       # 1-indexed within the current unit
    function_total: int       # number of functions in the current unit
    # Counts.
    units_total: int
    units_completed: int  # units that finished all rounds (or were abandoned)
    rounds_accepted: int  # cumulative across all units
    rounds_abandoned: int  # cumulative across all units
    # Budget consumed so far.
    elapsed_seconds: float
    tokens_used: int
    cost_usd: float
    # Termination state.
    halt_reason: Optional[str]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _unit_id(unit: CodeUnit) -> str:
    """Stable identifier for a code unit across rounds."""
    return f"{unit.original_path}::{unit.cell_index}"


class QALLMOrchestrator:
    def __init__(
            self,
            stage: LifecycleStage | str = LifecycleStage.IMPLEMENTATION,
            strategy: Strategy = "rl",
            llm_type: str = "openai",
            model_name: str | None = None,
            oracle: OracleType = "crash",
            rounds: int = 5,
            test_stability: str = "frozen",
            generation_policy: str = "grow",
            caps: BudgetCaps | None = None,
            judge_strategy: str = "lexicographic",
            profile: QualityProfile = IMPLEMENTATION_DEFAULT,
            repair_llm_type: str | None = None,
            repair_model_name: str | None = None,
            testgen_llm_type: str | None = None,
            testgen_model_name: str | None = None,
            run_id: str | None = None,
            reporter: QualityReporter | None = None,
    ) -> None:
        """Construct the orchestrator.

        The primary ``llm_type`` and ``model_name`` are the session's default
        model, used for any operation that doesn't specify its own. The four
        ``repair_*`` and ``testgen_*`` parameters allow callers to use
        different models for repair and test generation; if a ``repair_*``
        or ``testgen_*`` pair is left as ``None``, that subsystem inherits
        the default model.

        The judge always uses the default model (it sits between the two
        subsystems and is logically session-wide). This can be revisited
        later if model-specific judging becomes interesting.

        Run identity
        ------------
        Each orchestrator owns one :class:`QualityReporter` whose ``run_id``
        determines the output directory. Three ways to set it, in priority
        order:

        1. Pass a pre-built ``reporter``. The orchestrator uses it as is.
           This is the right path for the API: build the reporter at upload
           time, hand it to the orchestrator, and the same directory is
           used for the entire session no matter what.

        2. Pass a ``run_id`` string. A new reporter is built under
           ``outputs/quality_reporter/<run_id>``.

        3. Pass neither. A timestamp ``YYYYMMDD_HHMMSS`` is used. This is
           a convenience for one-shot scripts; it is NOT safe for long-lived
           sessions where the same orchestrator might be inadvertently
           reconstructed (each construction picks a fresh timestamp,
           producing surprising multiple folders).
        """
        self.ingestion_manager = IngestionManager()
        self.analysis_manager = AnalysisManager()
        # Captures every LLM prompt/response during run() for audit. The
        # reporter persists it per round; the API exposes it to the UI.
        self.transcript = TranscriptRecorder()
        if reporter is not None:
            self.reporter = reporter
        else:
            effective_run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
            self.reporter = QualityReporter("outputs/quality_reporter", effective_run_id)

        self.stage = stage if isinstance(stage, LifecycleStage) else LifecycleStage(stage)
        # Canonicalise the verifier name. ``rl`` is a legacy alias for the
        # iterative-feedback verifier; store ``feedback`` so reports and the
        # session schema use the current vocabulary. Behaviour is identical.
        self.strategy = "feedback" if strategy == "rl" else strategy
        self.oracle = oracle
        self.profile = profile

        # Budget caps: if not supplied, construct from the legacy `rounds`
        # argument plus default ceilings on the other axes.
        self.caps = caps or BudgetCaps.from_kwargs(max_rounds=rounds)
        self.rounds = self.caps.max_rounds
        self.current_round: int = 1

        # Progress-tracking state. These are written by the orchestrator
        # as it works and read by snapshot() (typically from a different
        # thread, when the API endpoint serves /api/jobs/{id}). We never
        # take a lock; primitive reads under the GIL are safe enough for
        # the fidelity the UI needs.
        self.current_phase: str = "initialising"
        self.current_stage: Optional[str] = None
        self.current_unit_id: Optional[str] = None
        # Function-level granularity inside verify. Updated via a callback
        # the orchestrator passes to verification_manager.verify().
        self.current_function: Optional[str] = None
        self.function_index: int = 0
        self.function_total: int = 0
        self.units_total: int = 0
        self.units_completed: int = 0

        self.stability_config = TestStabilityConfig.from_strings(
            stability=test_stability, policy=generation_policy
        )

        # Default (session-wide) LLM.
        provider_cls = LLM_PROVIDERS.get(llm_type, OpenAIModel)
        self.llm: LLMModel = provider_cls(model_name) if model_name else provider_cls()

        # Repair LLM: separate instance if specified, else reuse default.
        if repair_llm_type or repair_model_name:
            repair_cls = LLM_PROVIDERS.get(repair_llm_type or llm_type, OpenAIModel)
            self.repair_llm: LLMModel = (
                repair_cls(repair_model_name)
                if repair_model_name else repair_cls()
            )
        else:
            self.repair_llm = self.llm

        # Test-gen LLM: separate instance if specified, else reuse default.
        if testgen_llm_type or testgen_model_name:
            testgen_cls = LLM_PROVIDERS.get(testgen_llm_type or llm_type, OpenAIModel)
            self.testgen_llm: LLMModel = (
                testgen_cls(testgen_model_name)
                if testgen_model_name else testgen_cls()
            )
        else:
            self.testgen_llm = self.llm

        # Single tracker across all subsystems; the cost report aggregates
        # tokens regardless of which subsystem spent them. A future refinement
        # could attribute tokens per subsystem.
        self.tracker = TokenTracker(budget=self.caps.max_tokens)
        self.budget_state = BudgetState(caps=self.caps, tracker=self.tracker)
        self.halt_reason: HaltReason | None = None

        self.repair_manager = RepairManager(
            LLMRepairAgent(self.repair_llm), analyzer=self.analysis_manager
        )

        self.verification_manager = VerificationManager(
            llm=self.testgen_llm,
            tracker=self.tracker,
            oracle=self.oracle,
            total_rounds=self.rounds,
            stability_config=self.stability_config,
        )

        # Judge: built once, reused across all rounds and units. ModelJudge
        # needs the LLM; rule-based strategies ignore it.
        self.judge_strategy_name = judge_strategy
        self.judge = build_judge(
            judge_strategy, llm=self.llm, tracker=self.tracker
        )

        # Per-unit tracking populated as rounds run.
        self.tracks: dict[str, UnitTrack] = {}

        logger.info(
            "Initialization completed. Strategy=%s, judge=%s, "
            "stability=%s, policy=%s, caps=%s",
            self.strategy,
            self.judge_strategy_name,
            self.stability_config.stability.value,
            self.stability_config.policy.value,
            self.caps.to_dict(),
        )

    def run(self, source_path: str) -> dict:
        """Execute the full QALLM pipeline on a source path.

        Algorithm (per v3 sections 3 and 5, post baseline-verification change):
          Baseline (Round 0): For each code unit, analyse + verify the
            *original* source code. No repair. Produces a ProfileVerdict
            that becomes the first lineage entry. This is the ground
            truth against which round 1 is judged.
          Round N (1..max): For each code unit, analyse-repair-verify-judge
            decides whether the round's variant joins the unit's lineage
            (accepted) or its abandoned log (rejected). Judged against
            the parent (round 0 baseline for round 1; last accepted
            variant for round N >= 2).
        """
        logger.info(f"Starting QALLM operation for {source_path}...")

        # Activate prompt/response capture for the duration of this run.
        # reset_context clears any stale thread-local context from a prior
        # run on the same worker thread.
        reset_context()
        self._recorder_cm = active_recorder(self.transcript)
        self._recorder_cm.__enter__()

        # Reset state so a second call to run() on the same orchestrator
        # behaves identically to a first. Each run() owns one full
        # baseline-plus-rounds traversal; without this, calling run()
        # twice would start round numbering at N+1 and would not refill
        # per-unit tracks from a clean slate.
        # NOTE: current_round starts at 0 (baseline). After baseline
        # completes it becomes 1 and the repair loop starts.
        self.current_round = 0
        self.tracks.clear()
        self.halt_reason = None
        # Reset progress fields too so the UI does not see stale state
        # from a previous run.
        self.current_phase = "baseline"
        self.current_stage = None
        self.current_unit_id = None
        self.units_completed = 0
        # Budget state and tracker are intentionally NOT reset: a caller
        # who reuses the orchestrator should see the cumulative cost. If
        # truly independent runs are wanted, construct a new orchestrator.

        logger.info("Stage 0: Ingesting %s", source_path)
        units = self.ingestion_manager.collect(source_path)
        logger.info("Stage 0 completed! Collected %d code units.", len(units))
        self.units_total = len(units)

        # Initialise per-unit tracking before the first round runs.
        for unit in units:
            self.tracks[_unit_id(unit)] = UnitTrack(unit_id=_unit_id(unit))

        # ────── Round 0: baseline analyse + verify ──────
        # The baseline is the ground truth. Round 1 is judged against
        # the ProfileVerdict produced here. No repair is performed.
        logger.info("Round 0 (baseline): analyse + verify the original code")
        for unit in units:
            self._run_baseline_for_unit(unit)
        logger.info("Baseline complete. Round 0 stored on each unit's lineage.")
        # Baseline does NOT consume a budget round; max_rounds bounds
        # the number of *repair* rounds, not the baseline.
        self.current_phase = "rounds"
        self.current_round = 1

        # QALLM rounds: Analyse → Repair → Verify → Judge → Accept/Abandon.
        # Each unit independently advances its lineage or stalls on its
        # last accepted variant. Inputs for round 1 are the originals (the
        # round-0 baselines), then each subsequent round consumes the last
        # accepted variant.
        next_inputs: dict[str, CodeUnit] = {
            _unit_id(u): u for u in units
        }
        while True:
            self.budget_state.mark_round_start()
            next_inputs = self._run_round(next_inputs)
            self.budget_state.mark_round_end()

            self.current_round += 1
            # Under PER_ROUND, tests don't carry between rounds.
            self.verification_manager.store.clear_for_round()

            halt = self.budget_state.check()
            if halt is not None:
                self.halt_reason = halt
                if halt is HaltReason.MAX_ROUNDS:
                    logger.info("Completed all %d rounds.", self.caps.max_rounds)
                else:
                    logger.warning(
                        "Budget cap tripped: %s. Halting after round %d. "
                        "Spent: %d tokens, $%.4f, %.1fs total.",
                        halt.value,
                        self.budget_state.rounds_completed,
                        self.tracker.total_tokens,
                        self.tracker.total_cost_usd,
                        self.budget_state.elapsed_seconds,
                    )
                break

        self.current_phase = "summary"
        self.current_stage = None
        self.current_unit_id = None
        session_data = self.verification_manager.get_session_data()
        summary = self._build_summary(source_path, units, session_data)
        self.current_phase = "done"
        # Close the transcript recorder for this run.
        if getattr(self, "_recorder_cm", None) is not None:
            self._recorder_cm.__exit__(None, None, None)
            self._recorder_cm = None
        return summary

    def snapshot(self) -> OrchestratorProgress:
        """Read the orchestrator's current progress, safe across threads.

        The API calls this from the request thread while the orchestrator
        runs in a worker thread. We read primitive attributes only; no
        locks. The values may be a few milliseconds stale, which is fine
        for what the UI does with them.

        Counts are derived freshly each call from ``self.tracks`` rather
        than maintained as running totals, because lineage and abandoned
        entries are appended atomically and counting them is cheap.
        """
        rounds_accepted = sum(len(t.lineage) for t in self.tracks.values())
        rounds_abandoned = sum(len(t.abandoned) for t in self.tracks.values())
        return OrchestratorProgress(
            phase=self.current_phase,  # type: ignore[arg-type]
            current_round=self.current_round,
            total_rounds=self.rounds,
            current_stage=self.current_stage,  # type: ignore[arg-type]
            current_unit_id=self.current_unit_id,
            current_function=self.current_function,
            function_index=self.function_index,
            function_total=self.function_total,
            units_total=self.units_total,
            units_completed=self.units_completed,
            rounds_accepted=rounds_accepted,
            rounds_abandoned=rounds_abandoned,
            elapsed_seconds=self.budget_state.elapsed_seconds,
            tokens_used=self.tracker.total_tokens,
            cost_usd=self.tracker.total_cost_usd,
            halt_reason=self.halt_reason.value if self.halt_reason else None,
        )

    def _run_baseline_for_unit(self, unit: CodeUnit) -> None:
        """Run round 0 (baseline) for a single code unit.

        Round 0 analyses + verifies the original code; it does NOT call
        repair. A synthetic ``RepairedCodeUnit`` is constructed where the
        repaired source equals the original source so that ``verify`` can
        run unchanged. The resulting ProfileVerdict becomes the first
        entry in the unit's lineage, and is the parent against which
        round 1 will be judged.

        This is the change introduced for the "baseline verification"
        methodology decision: see docs/methodology-decisions.md.
        """
        unit_id = _unit_id(unit)
        track = self.tracks[unit_id]
        self.current_unit_id = unit_id

        # Step 1: static analysis on the original code. This is the same
        # call the analysis_manager makes during a normal round.
        self.current_stage = "analyse"
        analysed = self.analysis_manager.analyse_code_unit(unit)

        # Step 2: build a synthetic RepairedCodeUnit. The verify method
        # signature expects a RepairedCodeUnit (it uses
        # ``original_code_unit`` to filter "functions added by repair"
        # out of the test surface). For the baseline there is no repair,
        # so we wrap the analysed code with itself: repaired_source ==
        # original source, compiles == True, no diff. The construction
        # mirrors what repair_manager would have produced for an
        # identity transformation.
        identity_result = RepairResult(
            file_path=str(unit.original_path) if unit.original_path else "",
            repaired_source=unit.source_code,
            explanation="baseline: no repair applied (round 0)",
            compiles=True,
            unified_diff="",
        )
        baseline_repaired = RepairedCodeUnit(analysed, identity_result)

        # Step 3: verify the original. round_number=0 lets the test
        # stability store recognise this as the baseline round; under
        # FROZEN+REPLAY_ONLY (the default) this is exactly the round
        # in which tests are generated. Round 1+ then replays.
        self.current_stage = "verify"

        def _on_function_start(name: str, idx: int, total: int) -> None:
            self.current_function = name
            self.function_index = idx
            self.function_total = total

        tested_unit = self.verification_manager.verify(
            baseline_repaired,
            persist_dir=None,
            on_function_start=_on_function_start,
            round_number=0,
        )
        # Clear function-level fields so the next stage doesn't show
        # stale "verifying foo" while we're in judge.
        self.current_function = None
        self.function_index = 0
        self.function_total = 0

        # Step 4: build the ProfileVerdict from baseline evidence.
        self.current_stage = "judge"
        baseline_verdict = self._evaluate_profile_for(unit, tested_unit)

        # Step 5: record the baseline as the first lineage entry. There
        # is no judge verdict because there is no parent; that is the
        # only round in the entire run where judge_verdict is None.
        track.lineage.append(LineageEntry(
            round_number=0,
            code_unit=unit,
            verdict=baseline_verdict,
            judge_verdict=None,
        ))

        # Step 6: persist the baseline artefacts on disk. We route
        # through save_round_artefacts (the same call used for repair
        # rounds) so that disk layout is uniform: every round including
        # the baseline lives under lineage/round_NN/{unit_id}/ with the
        # same six files. The legacy save_baseline path is no longer
        # used by run(); kept on the reporter for backward compatibility
        # with callers that constructed reports outside the orchestrator.
        self.reporter.save_round_artefacts(
            round_number=0,
            unit_id=unit_id,
            code_unit=unit,
            analysed=analysed,
            tested=tested_unit,
            profile_verdict=baseline_verdict,
            judge_verdict_dict=None,
            accepted=True,
        )

        logger.info("  %s: baseline (round 0) recorded.", unit_id)

    def _run_round(
        self, inputs: dict[str, CodeUnit]
    ) -> dict[str, CodeUnit]:
        """Run one QALLM round across all units.

        Args:
            inputs: Mapping unit_id -> CodeUnit to process this round.
              Typically each unit's last accepted variant (or its original
              source on round 1).

        Returns:
            Mapping unit_id -> CodeUnit for the next round. Accepted units
            return their new variant; rejected units return their unchanged
            parent.
        """
        logger.info(
            "Round (%d of %d) started, %d unit(s)...",
            self.current_round, self.rounds, len(inputs),
        )
        next_inputs: dict[str, CodeUnit] = {}

        for unit_id, unit in inputs.items():
            track = self.tracks[unit_id]
            self.current_unit_id = unit_id
            set_context(round_number=self.current_round, unit_id=unit_id,
                        function=None, oracle=None)

            # Step 1: Analyse current variant.
            self.current_stage = "analyse"
            set_context(stage="analyse", role=None)
            analysed = self.analysis_manager.analyse_code_unit(unit)

            # Step 2: Repair.
            self.current_stage = "repair"
            set_context(stage="repair", role="repair")
            repaired = self.repair_manager.repair_code_unit(analysed)

            # Step 3: Verify.
            self.current_stage = "verify"
            set_context(stage="verify", role="testgen", oracle=self.oracle)

            def _on_function_start(name: str, idx: int, total: int) -> None:
                """Update orchestrator progress when verify enters each function.

                On slow local LLMs (gemma3:4b ~30-90s per call), an 8-function
                unit can spend 10+ minutes in verify. Without this callback
                the snapshot would show stale "current_function" for that
                entire window and the UI's inactivity timer could trip.
                """
                self.current_function = name
                self.function_index = idx
                self.function_total = total
                set_context(function=name)

            tested_unit = self.verification_manager.verify(
                repaired,
                persist_dir=None,  # reporter owns disk layout under NEW-07
                on_function_start=_on_function_start,
                round_number=self.current_round,
            )

            # Verify finished: clear function-level fields so the next stage
            # doesn't show stale "verifying foo" while we're in judge.
            self.current_function = None
            self.function_index = 0
            self.function_total = 0

            # Step 4: Build a ProfileVerdict for the variant.
            self.current_stage = "judge"
            set_context(stage="judge", role="judge", function=None, oracle=None)
            variant_unit = tested_unit.repaired_unit.repaired_code_unit
            variant_verdict = self._evaluate_profile_for(
                variant_unit, tested_unit
            )

            # Step 5 + 6: Judge and accept/abandon.
            # Post baseline-verification: every repair round (>= 1) has
            # a parent on the lineage because round 0 was recorded by
            # _run_baseline_for_unit. There is no longer an
            # "unconditionally accepted first round" case.
            parent = track.current_parent
            assert parent is not None, (
                f"Unit {unit_id}: no parent on lineage at round "
                f"{self.current_round}. Did baseline (round 0) run?"
            )

            judge_verdict = self.judge.decide(
                parent.verdict, variant_verdict,
                raw_evidence=self._raw_evidence_for(tested_unit),
            )
            if judge_verdict.outcome is JudgeOutcome.REGRESSION:
                accepted = False
                track.abandoned.append(AbandonedEntry(
                    round_number=self.current_round,
                    code_unit=variant_unit,
                    verdict=variant_verdict,
                    judge_verdict=judge_verdict,
                ))
                next_inputs[unit_id] = parent.code_unit
                logger.info(
                    "  %s: round %d REJECTED (%s); reverting to parent.",
                    unit_id, self.current_round, judge_verdict.outcome.value,
                )
            else:
                accepted = True
                track.lineage.append(LineageEntry(
                    round_number=self.current_round,
                    code_unit=variant_unit,
                    verdict=variant_verdict,
                    judge_verdict=judge_verdict,
                ))
                next_inputs[unit_id] = variant_unit
                logger.info(
                    "  %s: round %d ACCEPTED (%s).",
                    unit_id, self.current_round, judge_verdict.outcome.value,
                )

            # Step 7: persist the variant's full provenance bundle. The
            # accepted flag routes into lineage/ or abandoned/.
            improvement = build_improvement_report(
                round_number=self.current_round,
                unit_id=unit_id,
                accepted=accepted,
                parent_verdict=parent.verdict.to_dict(),
                variant_verdict=variant_verdict.to_dict(),
                parent_round=parent.round_number,
                judge_verdict=judge_verdict.to_dict(),
            )
            logger.info("  %s: %s", unit_id, improvement.headline())
            self.reporter.save_round_artefacts(
                round_number=self.current_round,
                unit_id=unit_id,
                code_unit=variant_unit,
                analysed=analysed,
                tested=tested_unit,
                profile_verdict=variant_verdict,
                judge_verdict_dict=judge_verdict.to_dict(),
                accepted=accepted,
                improvement_dict=improvement.to_dict(),
                transcript_records=[
                    r.to_dict() for r in self.transcript.for_round(self.current_round)
                    if r.context.get("unit_id") == unit_id
                ],
            )

        logger.info(
            "Round (%d of %d) completed.",
            self.current_round, self.rounds,
        )
        return next_inputs

    def _evaluate_profile_for(
        self, unit: CodeUnit, tested: TestedCodeUnit
    ) -> ProfileVerdict:
        """Build a ProfileVerdict for one code unit with all available context.

        Pulls project_root from the unit's path (the parent directory) and
        verification_sessions from the tested unit so reliability and
        FAIRness indicators have real numbers to consume.
        """
        project_root = (
            str(unit.original_path.parent)
            if unit.original_path is not None
            else None
        )
        context = {
            "project_root": project_root,
            "verification_sessions": list(tested.sessions),
        }
        return evaluate_profile(self.profile, unit.source_code, context=context)

    def _raw_evidence_for(self, tested: TestedCodeUnit) -> dict:
        """Compact raw verification numbers passed to ModelJudge as evidence."""
        sessions = tested.sessions
        return {
            "function_count": len(sessions),
            "pass_rates": [s.final_pass_rate for s in sessions],
            "bugs": [s.final_bugs for s in sessions],
            "coverage": [s.final_coverage for s in sessions],
        }

    def _build_summary(
        self,
        source_path: str,
        units: list[CodeUnit],
        sessions_data: list[dict],
    ) -> dict:
        # Per-unit lineage and abandoned summaries.
        tracks_dict = {uid: t.to_dict() for uid, t in self.tracks.items()}
        total_accepted = sum(len(t.lineage) for t in self.tracks.values())
        total_abandoned = sum(len(t.abandoned) for t in self.tracks.values())

        summary = {
            "source": source_path,
            "strategy": self.strategy,
            "judge_strategy": self.judge_strategy_name,
            "lifecycle_stage": self.stage.value,
            "oracle": self.oracle,
            "rounds_per_function": self.rounds,
            "model": "hypothesis" if self.strategy == "hypothesis" else self.llm.name(),
            "repair_model": self.repair_llm.name(),
            "testgen_model": self.testgen_llm.name(),
            # Quality profile metadata: which profile was applied and its
            # Quality profile metadata. The QualityProfile dataclass has a
            # to_dict() method that serialises profile_id, lifecycle_stage,
            # description, and the full dimension tree (each dimension with
            # its indicators). Trusting that method keeps the summary in
            # sync with the profile definition without us inventing fields.
            "profile": self.profile.to_dict(),
            "units_analyzed": len(units),
            "functions_verified": len(sessions_data),
            "rounds_accepted_total": total_accepted,
            "rounds_abandoned_total": total_abandoned,
            "cost": self.tracker.to_dict(),
            "budget": self.budget_state.summary(),
            "halt_reason": (
                self.halt_reason.value if self.halt_reason is not None else None
            ),
            "test_persistence": self.verification_manager.get_stability_summary(),
            "tracks": tracks_dict,
            "sessions": sessions_data,
        }
        summary_path = self.reporter.report_dir / "summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        # Derived human-readable views.
        from qallm.utils.views import write_views
        write_views(summary, self.reporter.report_dir)
        return summary