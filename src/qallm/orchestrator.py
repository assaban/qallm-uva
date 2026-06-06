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

from datetime import datetime
import json
import logging
import time
from typing import Literal, Optional

from qallm.analysis.normalizer import LifecycleStage
from qallm.ingestion.ingestion_manager import IngestionManager
from qallm.common.model import CodeUnit
from qallm.cost import BudgetCaps, BudgetState, HaltReason
from qallm.evaluation import ProfileVerdict, evaluate_profile
from qallm.improvement import build_improvement_report
from qallm.orchestrator_models import (
    AbandonedEntry,
    LineageEntry,
    OrchestratorProgress,
    UnitTrack,
    unit_id as _unit_id,
)
from qallm.judge import (
    JudgeOutcome,
    build_judge,
)
from qallm.llm.anthropic_provider import AnthropicModel
from qallm.llm.base import LLMModel, TokenTracker
from qallm.llm.ollama_provider import OllamaModel
from qallm.llm.openai_provider import OpenAIModel
from qallm.llm.fedllm_provider import FedLLMModel
from qallm.llm.transcript import (
    TranscriptRecorder,
    active_recorder,
    reset_context,
    set_context,
)
from qallm.profiles import IMPLEMENTATION_DEFAULT, QualityProfile
from qallm.utils.reporter import QualityReporter
from qallm.verification.models import OracleType, TestedCodeUnit
from test_persistence import TestStabilityConfig
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
    "fedllm": FedLLMModel,
}




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
            tags: list[str] | None = None,
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
        # User-supplied tags for grouping and retrieving sessions. Trimmed,
        # de-duplicated, blanks dropped; order preserved.
        self.tags: list[str] = []
        if tags:
            seen = set()
            for raw in tags:
                t = (raw or "").strip()
                if t and t not in seen:
                    seen.add(t)
                    self.tags.append(t)
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

        # One unified loop. Round 0 is the baseline (analyse + verify the
        # original, no repair, always accepted, no budget round consumed).
        # Rounds 1..max are repair rounds (analyse-repair-verify-judge).
        # _run_round -> _process_unit handles the round-0-vs-N differences;
        # there is no separate baseline method.
        next_inputs: dict[str, CodeUnit] = {_unit_id(u): u for u in units}

        # Round 0: baseline. Does not consume a budget round; max_rounds
        # bounds the number of repair rounds only.
        self.current_phase = "baseline"
        self.current_round = 0
        next_inputs = self._run_round(next_inputs)
        logger.info("Baseline complete. Round 0 stored on each unit's lineage.")

        # Rounds 1..max: repair loop.
        self.current_phase = "rounds"
        self.current_round = 1
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
            seconds_since_activity=max(
                0.0, time.monotonic() - self.tracker.last_activity
            ),
            halt_reason=self.halt_reason.value if self.halt_reason else None,
        )

    def _identity_repair(self, analysed) -> RepairedCodeUnit:
        """A no-op 'repair' whose output equals the input.

        Round 0 (baseline) verifies the *original* code, so there is no
        repair to perform. ``verify`` still expects a RepairedCodeUnit (it
        uses ``original_code_unit`` to filter functions the repair added
        out of the test surface), so we wrap the analysed code with itself:
        repaired_source == original, compiles == True, empty diff.
        """
        unit = analysed.code_unit
        identity_result = RepairResult(
            file_path=str(unit.original_path) if unit.original_path else "",
            repaired_source=unit.source_code,
            explanation="baseline: no repair applied (round 0)",
            compiles=True,
            unified_diff="",
        )
        return RepairedCodeUnit(analysed, identity_result)

    def _process_unit(
        self, unit_id: str, unit: CodeUnit, track: UnitTrack
    ) -> CodeUnit:
        """Process one code unit for the current round, return its next input.

        This is the single path for *every* round, including the baseline.
        The only differences between round 0 and rounds >= 1 are three
        small branches, all keyed on ``self.current_round == 0``:

          * Repair: round 0 uses an identity (no LLM call); rounds >= 1
            call the repair manager.
          * Judge: round 0 has no parent so there is no judge verdict and
            the result is unconditionally accepted; rounds >= 1 judge the
            variant against the parent and accept or abandon.
          * Improvement report: round 0 has nothing to compare against, so
            it is skipped; rounds >= 1 record parent-vs-variant deltas.

        Collapsing the former ``_run_baseline_for_unit`` into this method
        removes the analyse/verify/evaluate/persist duplication: baseline
        is simply "a round where repair is a no-op and the result is always
        accepted".
        """
        is_baseline = self.current_round == 0
        self.current_unit_id = unit_id
        set_context(round_number=self.current_round, unit_id=unit_id,
                    function=None, oracle=None)

        # Step 1: static analysis.
        self.current_stage = "analyse"
        set_context(stage="analyse", role=None)
        analysed = self.analysis_manager.analyse_code_unit(unit)

        # Step 2: repair (identity for the baseline, real otherwise).
        self.current_stage = "repair"
        if is_baseline:
            repaired = self._identity_repair(analysed)
        else:
            set_context(stage="repair", role="repair")
            repaired = self.repair_manager.repair_code_unit(analysed)

        # Step 3: verify. round_number=0 tells the stability store this is
        # the baseline round (where tests are generated under the default
        # FROZEN+REPLAY_ONLY policy; later rounds replay).
        self.current_stage = "verify"
        set_context(stage="verify", role="testgen", oracle=self.oracle)

        def _on_function_start(name: str, idx: int, total: int) -> None:
            # On slow local LLMs an 8-function unit can spend 10+ minutes
            # in verify; this keeps the snapshot's current_function live so
            # the UI inactivity timer does not trip.
            self.current_function = name
            self.function_index = idx
            self.function_total = total
            set_context(function=name)

        tested_unit = self.verification_manager.verify(
            repaired,
            persist_dir=None,  # reporter owns disk layout (NEW-07)
            on_function_start=_on_function_start,
            round_number=self.current_round,
        )
        self.current_function = None
        self.function_index = 0
        self.function_total = 0

        # Step 4: build the variant's ProfileVerdict.
        self.current_stage = "judge"
        set_context(stage="judge", role="judge", function=None, oracle=None)
        variant_unit = tested_unit.repaired_unit.repaired_code_unit
        variant_verdict = self._evaluate_profile_for(variant_unit, tested_unit)

        # Step 5: judge + accept/abandon (baseline is always accepted).
        parent = track.current_parent
        judge_verdict = None
        improvement = None

        if is_baseline:
            assert parent is None, (
                f"Unit {unit_id}: baseline ran but lineage was not empty."
            )
            accepted = True
            track.lineage.append(LineageEntry(
                round_number=0,
                code_unit=unit,
                verdict=variant_verdict,
                judge_verdict=None,
            ))
            next_input = variant_unit
            logger.info("  %s: baseline (round 0) recorded.", unit_id)
        else:
            assert parent is not None, (
                f"Unit {unit_id}: no parent at round {self.current_round}. "
                f"Did baseline (round 0) run?"
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
                next_input = parent.code_unit
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
                next_input = variant_unit
                logger.info(
                    "  %s: round %d ACCEPTED (%s).",
                    unit_id, self.current_round, judge_verdict.outcome.value,
                )

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

        # Step 6: persist the round bundle. Same disk layout for every
        # round including the baseline: lineage|abandoned/round_NN/{unit}/.
        self.reporter.save_round_artefacts(
            round_number=self.current_round,
            unit_id=unit_id,
            code_unit=variant_unit if not is_baseline else unit,
            analysed=analysed,
            tested=tested_unit,
            profile_verdict=variant_verdict,
            judge_verdict_dict=judge_verdict.to_dict() if judge_verdict else None,
            accepted=accepted,
            improvement_dict=improvement.to_dict() if improvement else None,
            transcript_records=[
                r.to_dict() for r in self.transcript.for_round(self.current_round)
                if r.context.get("unit_id") == unit_id
            ],
        )
        return next_input

    def _run_round(
        self, inputs: dict[str, CodeUnit]
    ) -> dict[str, CodeUnit]:
        """Run one round (baseline or repair) across all units.

        Round 0 is the baseline; rounds >= 1 are repair rounds. Per-unit
        work is identical in shape and lives in ``_process_unit``; this
        method just iterates and collects the next round's inputs.

        Args:
            inputs: unit_id -> CodeUnit to process this round. The last
              accepted variant per unit (the originals on round 0/1).

        Returns:
            unit_id -> CodeUnit for the next round.
        """
        label = "baseline" if self.current_round == 0 else "repair"
        logger.info(
            "Round %d (%s) started, %d unit(s)...",
            self.current_round, label, len(inputs),
        )
        next_inputs: dict[str, CodeUnit] = {}
        for unit_id, unit in inputs.items():
            track = self.tracks[unit_id]
            next_inputs[unit_id] = self._process_unit(unit_id, unit, track)
        logger.info("Round %d (%s) completed.", self.current_round, label)
        return next_inputs

    def _sonar_measures_for(self, unit: CodeUnit) -> dict | None:
        """Run SonarQube on a unit and return its measures, or None.

        SonarQube measures (the ISO/IEC 25010 ratings) cannot be recomputed
        cheaply inside an evaluator the way Bandit/Radon can, because they
        need a server round-trip. So when SonarQube is configured we run it
        here, on the *variant* being judged, and hand the measures to the
        profile via context. When it is not configured this is a no-op
        returning None, and the iso25010_base profile falls back to its
        Radon/Bandit indicators.
        """
        from qallm.analysis.sonarqube_analyzer import SonarQubeAnalyzer

        if not SonarQubeAnalyzer.is_configured():
            return None
        try:
            raw = SonarQubeAnalyzer().analyze(unit)
            payload = json.loads(raw.stdout) if raw.stdout else {}
            measures = payload.get("measures") or {}
            return measures or None
        except Exception:  # noqa: BLE001 - never break evaluation on sonar
            return None

    def _evaluate_profile_for(
        self, unit: CodeUnit, tested: TestedCodeUnit
    ) -> ProfileVerdict:
        """Build a ProfileVerdict for one code unit with all available context.

        Pulls project_root from the unit's path (the parent directory) and
        verification_sessions from the tested unit so reliability and
        FAIRness indicators have real numbers to consume. When a SonarQube
        server is configured, the unit's ISO/IEC 25010 ratings are added
        under ``sonar_measures`` so 25010 indicators can prefer them.
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
        sonar_measures = self._sonar_measures_for(unit)
        if sonar_measures is not None:
            context["sonar_measures"] = sonar_measures
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
            "tags": self.tags,
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