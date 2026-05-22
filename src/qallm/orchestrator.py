"""QALLM Orchestrator: the main pipeline conductor."""

from __future__ import annotations

import dataclasses
from datetime import datetime
import json
import logging
from typing import Literal

from qallm.analysis.normalizer import LifecycleStage
from qallm.config import settings
from qallm.ingestion.ingestion_manager import IngestionManager
from qallm.common.model import CodeUnit
from qallm.llm.anthropic_provider import AnthropicModel
from qallm.llm.base import LLMModel, TokenTracker
from qallm.llm.ollama_provider import OllamaModel
from qallm.llm.openai_provider import OpenAIModel
from qallm.utils.reporter import QualityReporter
from qallm.verification.models import OracleType
from qallm.analysis.analysis_manager import AnalysisManager
from qallm.repair.repair_manager import RepairManager
from qallm.repair.agents.llm_repair_agent import LLMRepairAgent
from qallm.verification.models import TestedCodeUnit

logger = logging.getLogger(__name__)

Strategy = Literal["rl", "oneshot", "hypothesis"]

LLM_PROVIDERS = {
    "ollama": OllamaModel,
    "openai": OpenAIModel,
    "anthropic": AnthropicModel,
}

# 1. Add the import at the top of orchestrator.py
from qallm.verification.verification_manager import VerificationManager
from qallm.verification.test_persistence import TestStabilityConfig
from qallm.cost import BudgetCaps, BudgetState, HaltReason


class QALLMOrchestrator:
    def __init__(
            self,
            stage: LifecycleStage = LifecycleStage.IMPLEMENTATION,
            strategy: Strategy = "rl",
            llm_type: str = "openai",
            model_name: str | None = None,
            oracle: OracleType = "crash",
            rounds: int = 5,
            test_stability: str = "frozen",
            generation_policy: str = "grow",
            caps: BudgetCaps | None = None,
    ) -> None:
        self.ingestion_manager = IngestionManager()
        self.analysis_manager = AnalysisManager()
        self.reporter = QualityReporter("outputs/quality_reporter", datetime.now().strftime("%Y%m%d_%H%M%S"))

        self.stage = stage
        self.strategy = strategy
        self.oracle = oracle

        # Budget caps: if not supplied, construct from the legacy `rounds`
        # argument plus default ceilings on the other axes. `rounds` is
        # kept as a positional parameter for backward compatibility with
        # earlier orchestrator clients (web UI, tests) that don't yet pass
        # a full BudgetCaps.
        self.caps = caps or BudgetCaps.from_kwargs(max_rounds=rounds)
        # Legacy: keep `self.rounds` as an alias for caps.max_rounds so
        # downstream code that reads it still works.
        self.rounds = self.caps.max_rounds
        self.current_round: int = 1

        # Test-stability config: validated here so a bad combination fails
        # at orchestrator construction rather than mid-run.
        self.stability_config = TestStabilityConfig.from_strings(
            stability=test_stability, policy=generation_policy
        )

        provider_cls = LLM_PROVIDERS.get(llm_type, OpenAIModel)
        self.llm: LLMModel = provider_cls(model_name) if model_name else provider_cls()
        # The token tracker's own budget mirrors the cost-caps token budget,
        # so the per-LLM-call "stop on out-of-tokens" logic still works.
        self.tracker = TokenTracker(budget=self.caps.max_tokens)
        # Budget state: tracks elapsed time and round count for cap checks.
        self.budget_state = BudgetState(caps=self.caps, tracker=self.tracker)
        # Set on halt; null until then.
        self.halt_reason: HaltReason | None = None

        # 2. Initialize Repair Manager
        self.repair_manager = RepairManager(LLMRepairAgent(self.llm), analyzer=self.analysis_manager)

        # Initialize Verification Manager with the round limit and stability config
        self.verification_manager = VerificationManager(
            llm=self.llm,
            tracker=self.tracker,
            oracle=self.oracle,
            total_rounds=self.rounds,
            stability_config=self.stability_config,
        )

        logger.info(
            "Initialization completed! Strategy %s, stability %s, policy %s, caps %s",
            self.strategy,
            self.stability_config.stability.value,
            self.stability_config.policy.value,
            self.caps.to_dict(),
        )

    def run(self, source_path: str) -> dict:
        """Execute the full QALLM pipeline on a source path.

        Algorithm (Option A):
          Baseline (Round 0): Analyse original code → store as baseline
          Round N (1..max):   Repair → Analyse → Verify → Report
        """
        logger.info(f"Starting QALLM operation for {source_path}...")

        # Stage 0: Ingestion
        logger.info("Stage 0: Ingesting %s", source_path)
        units = self.ingestion_manager.collect(source_path)
        logger.info("Stage 0 completed! Collected %d code units.", len(units))

        # Baseline (Round 0): Analyse only, no repair, no tests
        logger.info("Baseline (Round 0): Static analysis on original code")
        for unit in units:
            analysed = self.analysis_manager.analyse_code_unit(unit)
            self.reporter.save_static_report(analysed, "round_00_baseline")
        logger.info("Baseline complete. Stored as round_00_baseline.")

        # QALLM rounds: Repair → Analyse → Verify → Report
        # Loop terminates when either max_rounds is reached or any other
        # budget cap trips at a round boundary.
        round_cus_to_process = units
        while True:
            self.budget_state.mark_round_start()
            round_cus_tested = self.run_round(round_cus_to_process)
            self.budget_state.mark_round_end()

            next_round_cus_to_process = [tcu.repaired_unit.repaired_code_unit for tcu in round_cus_tested]
            round_cus_to_process = next_round_cus_to_process
            self.current_round += 1
            # Under PER_ROUND, tests don't carry between rounds. Drop them
            # so the next round starts with an empty store. No-op for FROZEN.
            self.verification_manager.store.clear_for_round()

            # Cap check at the round boundary. The first cap to trip wins;
            # MAX_ROUNDS is the natural completion signal.
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

    def run_round(self, units: list[CodeUnit]) -> list[TestedCodeUnit]:
        logger.info(f"Round ({self.current_round} of {self.rounds}) started...")
        round_suffix = self._construct_round_suffix()
        persist_dir = self.reporter.report_dir / round_suffix
        results = []

        for unit in units:
            # Step 1: Analyse current code state
            analysed = self.analysis_manager.analyse_code_unit(unit)
            self.reporter.save_static_report(analysed, round_suffix)

            # Step 2: Repair findings from analysis
            repaired = self.repair_manager.repair_code_unit(analysed)
            self.reporter.save_static_repair_artifacts(repaired, round_suffix)

            # Step 3: Verify (generates tests, executes, scores)
            # persist_dir enables incremental saving after each function
            tested_unit = self.verification_manager.verify(
                repaired, persist_dir=persist_dir, round_number=self.current_round
            )
            self.reporter.save_verification_artifacts(tested_unit, round_suffix)

            results.append(tested_unit)
        logger.info(f"Round ({self.current_round} of {self.rounds}) completed!")
        return results

    def _construct_round_suffix(self) -> str:
        round_suffix: str = f"round_{self.current_round:02d}"
        return round_suffix

    def _build_summary(self, source_path: str, units: list[CodeUnit], sessions_data: list[dict]) -> dict:
        summary = {
            "source": source_path,
            "strategy": self.strategy,
            "lifecycle_stage": self.stage.value,
            "oracle": self.oracle,
            "rounds_per_function": self.rounds,
            "model": "hypothesis" if self.strategy == "hypothesis" else self.llm.name(),
            "units_analyzed": len(units),
            "functions_verified": len(sessions_data),
            "cost": self.tracker.to_dict(),
            "budget": self.budget_state.summary(),
            "halt_reason": (
                self.halt_reason.value if self.halt_reason is not None else None
            ),
            "test_persistence": self.verification_manager.get_stability_summary(),
            "sessions": sessions_data,
        }
        summary_path = self.reporter.report_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary
