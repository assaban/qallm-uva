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


class QALLMOrchestrator:
    def __init__(
            self,
            stage: LifecycleStage = LifecycleStage.IMPLEMENTATION,
            strategy: Strategy = "rl",
            llm_type: str = "openai",
            model_name: str | None = None,
            oracle: OracleType = "crash",
            rounds: int = 5,
    ) -> None:
        self.ingestion_manager = IngestionManager()
        self.analysis_manager = AnalysisManager()
        self.reporter = QualityReporter("/tmp/outputs/quality_reporter", datetime.now().strftime("%Y%m%d_%H%M%S"))

        self.stage = stage
        self.strategy = strategy
        self.oracle = oracle
        self.rounds = 1 if rounds < 1 else rounds
        self.current_round: int = 1

        provider_cls = LLM_PROVIDERS.get(llm_type, OpenAIModel)
        self.llm: LLMModel = provider_cls(model_name) if model_name else provider_cls()
        self.tracker = TokenTracker(budget=settings.TOKEN_BUDGET)

        # 2. Initialize Repair Manager
        self.repair_manager = RepairManager(LLMRepairAgent(self.llm), analyzer=self.analysis_manager)

        # Initialize Verification Manager with the round limit from the CLI/settings[cite: 36]
        self.verification_manager = VerificationManager(
            llm=self.llm,
            tracker=self.tracker,
            oracle=self.oracle,
            total_rounds=self.rounds  # Pass the parameter here[cite: 36]
        )

        logger.info(f"Initialization completed! Strategy {self.strategy}")

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
        round_cus_to_process = units
        while self.current_round <= self.rounds:
            round_cus_tested = self.run_round(round_cus_to_process)
            next_round_cus_to_process = [tcu.repaired_unit.repaired_code_unit for tcu in round_cus_tested]
            round_cus_to_process = next_round_cus_to_process
            self.current_round += 1

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
                repaired, persist_dir=persist_dir
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
            "sessions": sessions_data,
        }
        summary_path = self.reporter.report_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary
