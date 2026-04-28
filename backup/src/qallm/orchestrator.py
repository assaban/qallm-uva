"""QALLM Orchestrator: the main pipeline.

Maps directly to the thesis architecture (Section 3.4):
  Stage 1: Jupyter Preprocessing (ingestion)
  Stage 2: Static Quality Analysis (analysis)
  Stage 3: RL-Based Verification (verification loop)
  Stage 4: Quality Reporting (reporter)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

from qallm.analysis.metrics import StaticAnalyzer
from qallm.analysis.normalizer import LifecycleNormalizer, LifecycleStage
from qallm.config import settings
from qallm.ingestion.parsers import CodeUnit, IngestionManager
from qallm.llm.anthropic_provider import AnthropicModel
from qallm.llm.base import LLMModel, TokenTracker
from qallm.llm.ollama_provider import OllamaModel
from qallm.llm.openai_provider import OpenAIModel
from qallm.utils.reporter import QualityReporter
from qallm.verification.extractor import extract_functions_from_source
from qallm.verification.loop import TestGenerationLoop, save_session
from qallm.verification.models import OracleType

logger = logging.getLogger(__name__)


LLM_PROVIDERS = {
    "openai": OpenAIModel,
    "anthropic": AnthropicModel,
    "ollama": OllamaModel,
}


class QALLMOrchestrator:
    """The Conductor: ingestion -> static analysis -> RL verification -> reporting."""

    def __init__(
        self,
        stage: LifecycleStage = LifecycleStage.IMPLEMENTATION,
        llm_type: str = "openai",
        model_name: str | None = None,
        oracle: OracleType = "crash",
        rounds: int = 5,
    ) -> None:
        self.ingestion = IngestionManager()
        self.analyzer = StaticAnalyzer()
        self.normalizer = LifecycleNormalizer()
        self.reporter = QualityReporter()
        self.stage = stage
        self.oracle = oracle
        self.rounds = rounds

        # Build LLM
        provider_cls = LLM_PROVIDERS.get(llm_type, OpenAIModel)
        self.llm: LLMModel = provider_cls(model_name) if model_name else provider_cls()
        self.tracker = TokenTracker(budget=settings.TOKEN_BUDGET)

    def run(self, source_path: str) -> dict:
        """Execute the full QALLM pipeline on a source path.

        Returns a dict with static_reports, verification_sessions, and cost_summary.
        """
        # Stage 1: Ingestion
        logger.info("Stage 1: Ingesting %s", source_path)
        units = self.ingestion.collect(source_path)
        logger.info("Collected %d code units", len(units))

        # Stage 2: Static Analysis
        logger.info("Stage 2: Running static analysis")
        static_reports = self.analyzer.analyze(units)
        self.reporter.save_static_report(static_reports)

        # Stage 3: RL Verification
        logger.info("Stage 3: RL verification loop (%d rounds, oracle=%s)", self.rounds, self.oracle)
        sessions = []

        for unit, report in zip(units, static_reports):
            lifecycle_status = self.normalizer.evaluate(report["metrics"], self.stage)
            functions = extract_functions_from_source(unit.source, str(unit.original_path))

            if not functions:
                logger.info("No extractable functions in %s (cell %d), skipping verification",
                            unit.original_path.name, unit.cell_index)
                continue

            loop = TestGenerationLoop(
                llm=self.llm,
                rounds=self.rounds,
                oracle=self.oracle,
                tracker=self.tracker,
            )

            for func in functions:
                module_name = f"source_{unit.original_path.stem}_c{unit.cell_index}"
                persist_dir = self.reporter.report_dir / "generated_tests"

                session = loop.run(
                    func=func,
                    source_code=unit.source,
                    module_name=module_name,
                    persist_dir=persist_dir,
                    source_origin=unit.original_path,
                )

                # Save session JSON for reproducibility
                session_path = self.reporter.report_dir / f"session_{func.name}.json"
                save_session(session, session_path)
                sessions.append(session)

                # Log progress
                logger.info(
                    "  %s: %d rounds, coverage=%.1f%%, bugs=%d, curve=%s",
                    func.name,
                    len(session.rounds),
                    session.final_coverage or 0.0,
                    session.final_bugs,
                    session.learning_curve,
                )

        # Stage 4: Reporting
        summary = {
            "source": source_path,
            "lifecycle_stage": self.stage.value,
            "oracle": self.oracle,
            "rounds_per_function": self.rounds,
            "model": self.llm.name(),
            "units_analyzed": len(units),
            "functions_verified": len(sessions),
            "cost": self.tracker.to_dict(),
            "sessions": [
                {
                    "function": s.function_name,
                    "final_coverage": s.final_coverage,
                    "final_bugs": s.final_bugs,
                    "learning_curve": s.learning_curve,
                    "rounds_completed": len(s.rounds),
                }
                for s in sessions
            ],
        }

        summary_path = self.reporter.report_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        logger.info("Results saved to %s", self.reporter.report_dir)

        return summary