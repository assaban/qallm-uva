"""QALLM Orchestrator: the main pipeline conductor."""

from __future__ import annotations

import json
import logging
import difflib
from pathlib import Path
from typing import Literal, List, Dict

from qallm.analysis.analysis_model import Finding
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
from qallm.analysis.analysis_orchestration import AnalysisManager
from qallm.repair.repair_orchestration import RepairManager
from qallm.repair.agents.llm_repair_agent import LLMRepairAgent

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
        self.analyzer = AnalysisManager()

        self.normalizer = LifecycleNormalizer()
        self.reporter = QualityReporter()
        self.stage = stage
        self.strategy = strategy
        self.oracle = oracle
        self.rounds = 1 if strategy == "oneshot" else rounds

        provider_cls = LLM_PROVIDERS.get(llm_type, OpenAIModel)
        self.llm: LLMModel = provider_cls(model_name) if model_name else provider_cls()
        self.tracker = TokenTracker(budget=settings.TOKEN_BUDGET)

        # Initialize Repair Manager with the LLM Agent
        self.repairManager = RepairManager(LLMRepairAgent(self.llm), analyzer=self.analyzer)

    def run(self, source_path: str) -> dict:
        """Execute the full QALLM pipeline on a source path."""

        # Stage 1: Ingestion
        logger.info("Stage 1: Ingesting %s", source_path)
        units = self.ingestion.collect(source_path)
        logger.info("Collected %d code units", len(units))

        # Stage 2: Static Analysis
        logger.info("Stage 2: Running initial static analysis")
        static_findings: List[Finding] = self.analyzer.analyze(units)
        self.reporter.save_static_report(static_findings)

        # --- REPAIR STAGE ---
        source_code_map: Dict[str, str] = {
            (str(u.original_path.absolute()) if u.original_path else "cell.py"): u.source
            for u in units
        }

        logger.info("Repair Stage: Processing %d findings", len(static_findings))
        repair_results = self.repairManager.process_repairs(
            findings=static_findings,
            source_code_map=source_code_map
        )

        # Track if we need to re-analyze findings guide verification
        any_repaired = False
        for res in repair_results:
            path_key = res.file_path
            filename = Path(path_key).name

            # --- Handling Unclean Code (Self-Correction Retry) ---
            if not res.compiles:
                logger.warning("  Repair for %s failed validation. Retrying with error context...", filename)
                # repeat the request with context of the failure (logic handled in manager or here)
                # For this version, we trigger a manual second-shot repair
                res = self.repairManager.process_repairs(
                    findings=[f for f in static_findings if f.file == path_key],
                    source_code_map=source_code_map
                    # In future, the Manager could accept a 'retry_with_error' parameter
                )[0]

            if res.compiles:
                any_repaired = True
                orig_source = source_code_map[path_key]

                # Update the source in the unit and map so Stage 3 uses it
                for unit in units:
                    if (str(unit.original_path.absolute()) if unit.original_path else "cell.py") == path_key:
                        unit.source = res.repaired_source
                source_code_map[path_key] = res.repaired_source

                # --- Diff Generation & Artifact Storage ---
                diff = difflib.unified_diff(
                    orig_source.splitlines(keepends=True),
                    res.repaired_source.splitlines(keepends=True),
                    fromfile=f"original/{filename}",
                    tofile=f"repaired/{filename}"
                )
                diff_text = "".join(diff)

                self._save_repair_artifacts(filename, orig_source, res.repaired_source, diff_text)
                logger.info("  Repair for %s: ✅ CLEAN (Diff saved)", filename)
            else:
                logger.error("  Repair for %s: ❌ FAILED (Could not compile)", filename)

        # Re-analyze if changes were made so verification isguided by the NEW state
        if any_repaired:
            logger.info("Post-Repair: Refreshing static analysis for verification guidance")
            new_static_findings = self.analyzer.analyze(units)
            logger.info("Post-Repair: Found %d findings. Before findings count: %d", len(new_static_findings), len(static_findings))


        # Stage 3: Verification
        if self.strategy == "hypothesis":
            sessions_data = self._run_hypothesis(units)
        else:
            sessions_data = self._run_llm_verification(units, static_findings)

        # Stage 4: Reporting
        return self._build_summary(source_path, units, sessions_data)

    def _save_repair_artifacts(self, filename: str, original: str, repaired: str, diff: str):
        """Stores original, repaired, and diff files in the report directory."""
        repair_dir = self.reporter.report_dir / "repairs"
        repair_dir.mkdir(parents=True, exist_ok=True)

        stem = Path(filename).stem
        (repair_dir / f"{stem}_original.py").write_text(original, encoding="utf-8")
        (repair_dir / f"{stem}_repaired.py").write_text(repaired, encoding="utf-8")
        (repair_dir / f"{stem}_diff.txt").write_text(diff, encoding="utf-8")

    def _run_hypothesis(self, units: list[CodeUnit]) -> list[dict]:
        from qallm.verification.hypothesis_baseline import run_hypothesis_baseline
        all_results = []
        for unit in units:
            source_filename = f"source_{unit.original_path.stem}_c{unit.cell_index}.py"
            results = run_hypothesis_baseline(
                source_code=unit.source,
                source_filename=source_filename,
                source_origin=unit.original_path,
            )
            for r in results:
                all_results.append({
                    "function": r["function"],
                    "final_coverage": r["coverage"],
                    "final_bugs": r["bugs_found"],
                    "learning_curve": [],
                    "rounds_completed": 1,
                    "strategy": "hypothesis",
                })
        return all_results

    def _run_llm_verification(self, units: list[CodeUnit], static_findings: list[Finding]) -> list[dict]:
        logger.info("Stage 3: RL verification loop (%d rounds), oracle=%s", self.rounds, self.oracle)
        sessions_data = []
        for unit in units:
            functions = extract_functions_from_source(unit.source, str(unit.original_path))
            if not functions: continue

            loop = TestGenerationLoop(llm=self.llm, rounds=self.rounds, oracle=self.oracle, tracker=self.tracker)
            for func in functions:
                module_name = f"source_{unit.original_path.stem}_c{unit.cell_index}"
                session = loop.run(
                    func=func, source_code=unit.source,
                    module_name=module_name,
                    persist_dir=self.reporter.report_dir / "generated_tests",
                    source_origin=unit.original_path
                )
                save_session(session, self.reporter.report_dir / f"session_{func.name}.json")
                sessions_data.append({
                    "function": session.function_name,
                    "final_coverage": session.final_coverage,
                    "final_bugs": session.final_bugs,
                    "learning_curve": session.learning_curve,
                    "rounds_completed": len(session.rounds),
                    "strategy": self.strategy,
                })
        return sessions_data

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