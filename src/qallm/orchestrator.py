"""QALLM Orchestrator: the main pipeline conductor.

Per workflow design v3 sections 3, 5, and 9.3. The orchestrator runs
QALLM rounds and decides per code unit whether each round's variant is
accepted or abandoned.

Loop shape
----------

.. code-block:: text

    Round 0 (Baseline):    Static analysis only; no repair, no verify.
                           Used as the round-0 marker for reports.
    Round 1..N:
      for each code unit:
        1. Analyse current variant (or unit if round 1).
        2. Repair based on analysis.
        3. Verify (generate or replay tests; record session).
        4. Build a ProfileVerdict for the variant.
        5. Judge variant vs parent (the last accepted variant for this unit,
           or None on round 1).
        6. If IMPROVEMENT or NO_CHANGE: variant becomes parent of next round.
           If REGRESSION: variant is logged as abandoned; parent stays.

A unit's "lineage" is the chain of accepted variants. A unit's "abandoned"
list grows with each rejected variant. Round 1 is always accepted (no
parent to compare against).
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
from qallm.profiles import IMPLEMENTATION_DEFAULT, QualityProfile
from qallm.utils.reporter import QualityReporter
from qallm.verification.models import OracleType, TestedCodeUnit
from qallm.verification.test_persistence import TestStabilityConfig
from qallm.verification.verification_manager import VerificationManager
from qallm.analysis.analysis_manager import AnalysisManager
from qallm.repair.repair_manager import RepairManager
from qallm.repair.agents.llm_repair_agent import LLMRepairAgent

logger = logging.getLogger(__name__)

Strategy = Literal["rl", "oneshot", "hypothesis"]

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
    judge_verdict: Optional[JudgeVerdict] = None  # None for round 1

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
        """
        self.ingestion_manager = IngestionManager()
        self.analysis_manager = AnalysisManager()
        self.reporter = QualityReporter("outputs/quality_reporter", datetime.now().strftime("%Y%m%d_%H%M%S"))

        self.stage = stage if isinstance(stage, LifecycleStage) else LifecycleStage(stage)
        self.strategy = strategy
        self.oracle = oracle
        self.profile = profile

        # Budget caps: if not supplied, construct from the legacy `rounds`
        # argument plus default ceilings on the other axes.
        self.caps = caps or BudgetCaps.from_kwargs(max_rounds=rounds)
        self.rounds = self.caps.max_rounds
        self.current_round: int = 1

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

        Algorithm (per v3 sections 3 and 5):
          Baseline (Round 0): Static analysis on original code; stored as
            a separate artefact for reports. No repair, no verify, no judge.
          Round N (1..max): For each code unit, repair-analyse-verify-judge
            decides whether the round's variant joins the unit's lineage
            (accepted) or its abandoned log (rejected).
        """
        logger.info(f"Starting QALLM operation for {source_path}...")

        logger.info("Stage 0: Ingesting %s", source_path)
        units = self.ingestion_manager.collect(source_path)
        logger.info("Stage 0 completed! Collected %d code units.", len(units))

        # Initialise per-unit tracking before the first round runs.
        for unit in units:
            self.tracks[_unit_id(unit)] = UnitTrack(unit_id=_unit_id(unit))

        logger.info("Baseline (Round 0): Static analysis on original code")
        for unit in units:
            analysed = self.analysis_manager.analyse_code_unit(unit)
            self.reporter.save_baseline(analysed)
        logger.info("Baseline complete. Stored as round_00_baseline.")

        # QALLM rounds: Repair → Analyse → Verify → Judge → Accept/Abandon.
        # Each unit independently advances its lineage or stalls on its
        # last accepted variant.
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

        session_data = self.verification_manager.get_session_data()
        summary = self._build_summary(source_path, units, session_data)
        return summary

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

            # Step 1: Analyse current variant.
            analysed = self.analysis_manager.analyse_code_unit(unit)

            # Step 2: Repair.
            repaired = self.repair_manager.repair_code_unit(analysed)

            # Step 3: Verify.
            tested_unit = self.verification_manager.verify(
                repaired,
                persist_dir=None,  # reporter owns disk layout under NEW-07
                round_number=self.current_round,
            )

            # Step 4: Build a ProfileVerdict for the variant.
            variant_unit = tested_unit.repaired_unit.repaired_code_unit
            variant_verdict = self._evaluate_profile_for(
                variant_unit, tested_unit
            )

            # Step 5 + 6: Judge and accept/abandon.
            parent = track.current_parent
            if parent is None:
                # Round 1: no parent yet. Unconditional acceptance.
                judge_verdict = None
                accepted = True
                track.lineage.append(LineageEntry(
                    round_number=self.current_round,
                    code_unit=variant_unit,
                    verdict=variant_verdict,
                    judge_verdict=None,
                ))
                next_inputs[unit_id] = variant_unit
                logger.info(
                    "  %s: round 1 accepted unconditionally", unit_id,
                )
            else:
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
            self.reporter.save_round_artefacts(
                round_number=self.current_round,
                unit_id=unit_id,
                code_unit=variant_unit,
                analysed=analysed,
                tested=tested_unit,
                profile_verdict=variant_verdict,
                judge_verdict_dict=(
                    judge_verdict.to_dict() if judge_verdict is not None else None
                ),
                accepted=accepted,
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
