"""QALLM Orchestrator: the main pipeline.

Maps directly to the thesis architecture (Section 3.4):
  Stage 1: Jupyter Preprocessing (ingestion)
  Stage 2: Static Quality Analysis (analysis)
  Stage 3: RL-Based Verification (verification loop)
  Stage 4: Quality Reporting (reporter)

Supports three test generation strategies (Section 4.2):
  (a) hypothesis: Property-based testing, no LLM (baseline)
  (b) oneshot:    LLM with 1 round, no feedback (ablation)
  (c) rl:         LLM with N rounds and feedback (proposed method)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

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

Strategy = Literal["rl", "oneshot", "hypothesis"]

LLM_PROVIDERS = {
    "openai": OpenAIModel,
    "anthropic": AnthropicModel,
    "ollama": OllamaModel,
}


class QALLMOrchestrator:
    """The Conductor: ingestion -> static analysis -> verification -> reporting."""

    def __init__(
            self,
            stage: LifecycleStage = LifecycleStage.IMPLEMENTATION,
            strategy: Strategy = "rl",
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
        self.strategy = strategy
        self.oracle = oracle

        # Oneshot is just RL with rounds forced to 1
        if strategy == "oneshot":
            self.rounds = 1
        else:
            self.rounds = rounds

        # Build LLM (not needed for hypothesis, but harmless to create)
        provider_cls = LLM_PROVIDERS.get(llm_type, OpenAIModel)
        self.llm: LLMModel = provider_cls(model_name) if model_name else provider_cls()
        self.tracker = TokenTracker(budget=settings.TOKEN_BUDGET)

    def run(self, source_path: str) -> dict:
        """Execute the full QALLM pipeline on a source path."""

        # Stage 1: Ingestion
        logger.info("Stage 1: Ingesting %s", source_path)
        units = self.ingestion.collect(source_path)
        logger.info("Collected %d code units", len(units))

        # Stage 2: Static Analysis
        logger.info("Stage 2: Running static analysis")
        static_reports = self.analyzer.analyze(units)
        self.reporter.save_static_report(static_reports)

        # Stage 3: Verification (strategy-dependent)
        if self.strategy == "hypothesis":
            sessions_data = self._run_hypothesis(units)
        else:
            sessions_data = self._run_llm_verification(units, static_reports)

        # Stage 4: Reporting
        return self._build_summary(source_path, units, sessions_data)

    # ──────────────────────────────────────────────
    # Strategy (a): Hypothesis baseline, no LLM
    # ──────────────────────────────────────────────

    def _run_hypothesis(self, units: list[CodeUnit]) -> list[dict]:
        """Run Hypothesis property-based testing on all functions."""
        from qallm.verification.hypothesis_baseline import run_hypothesis_baseline

        logger.info("Stage 3: Hypothesis baseline (no LLM)")
        all_results = []

        for unit in units:
            source_filename = f"source_{unit.original_path.stem}_c{unit.cell_index}.py"

            results = run_hypothesis_baseline(
                source_code=unit.source,
                source_filename=source_filename,
                source_origin=unit.original_path,
            )

            for r in results:
                # Save generated test code for reproducibility
                test_path = self.reporter.report_dir / "generated_tests" / f"hyp_{r['function']}.py"
                test_path.parent.mkdir(parents=True, exist_ok=True)
                test_path.write_text(r.get("test_code", ""), encoding="utf-8")

                all_results.append({
                    "function": r["function"],
                    "final_coverage": r["coverage"],
                    "final_bugs": r["bugs_found"],
                    "learning_curve": [],
                    "rounds_completed": 1,
                    "strategy": "hypothesis",
                })

                logger.info(
                    "  %s: coverage=%.1f%%, bugs=%d",
                    r["function"],
                    r["coverage"] or 0.0,
                    r["bugs_found"],
                )

        return all_results

    # ──────────────────────────────────────────────
    # Strategy (b) and (c): LLM-based verification
    # ──────────────────────────────────────────────

    def _run_llm_verification(self, units: list[CodeUnit], static_reports: list[dict]) -> list[dict]:
        """Run LLM verification (oneshot or RL with feedback)."""
        label = "One-shot LLM" if self.strategy == "oneshot" else f"RL verification loop ({self.rounds} rounds)"
        logger.info("Stage 3: %s, oracle=%s", label, self.oracle)

        sessions_data = []

        for unit, report in zip(units, static_reports):
            lifecycle_status = self.normalizer.evaluate(report["metrics"], self.stage)
            functions = extract_functions_from_source(unit.source, str(unit.original_path))

            if not functions:
                logger.info("No extractable functions in %s (cell %d), skipping",
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

                # Save session JSON
                session_path = self.reporter.report_dir / f"session_{func.name}.json"
                save_session(session, session_path)

                sessions_data.append({
                    "function": session.function_name,
                    "final_coverage": session.final_coverage,
                    "final_bugs": session.final_bugs,
                    "learning_curve": session.learning_curve,
                    "rounds_completed": len(session.rounds),
                    "strategy": self.strategy,
                })

                logger.info(
                    "  %s: %d rounds, coverage=%.1f%%, bugs=%d, curve=%s",
                    func.name,
                    len(session.rounds),
                    session.final_coverage or 0.0,
                    session.final_bugs,
                    session.learning_curve,
                )

        return sessions_data

    # ──────────────────────────────────────────────
    # Stage 4: Build summary
    # ──────────────────────────────────────────────

    def _build_summary(self, source_path: str, units: list[CodeUnit], sessions_data: list[dict]) -> dict:
        """Build and save the final summary JSON."""
        summary = {
            "source": source_path,
            "strategy": self.strategy,
            "lifecycle_stage": self.stage.value,
            "oracle": self.oracle,
            "rounds_per_function": self.rounds,
            "model": "hypothesis (no LLM)" if self.strategy == "hypothesis" else self.llm.name(),
            "units_analyzed": len(units),
            "functions_verified": len(sessions_data),
            "cost": self.tracker.to_dict(),
            "sessions": sessions_data,
        }

        summary_path = self.reporter.report_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        logger.info("Results saved to %s", self.reporter.report_dir)

        return summary
