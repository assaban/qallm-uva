from typing import List, Dict, Any
from pathlib import Path
from qallm.ingestion.parsers import IngestionManager
from qallm.stage1_qqe.metrics import StaticAnalyzer
from qallm.stage1_qqe.normalizer import LifecycleNormalizer, LifecycleStage
from qallm.stage2_lre.prompter import PromptConstructor, EvidenceBundle
from qallm.stage2_lre.verifier import VerificationRunner, VerificationResult
from qallm.stage2_lre.clients import OpenAIClient, GemmaClient, AnthropicClient
from qallm.utils.reporter import QualityReporter
from qallm.utils.signatures import get_code_signatures


class QALLMOrchestrator:
    """The Conductor - Fully synchronized with reporting and verification logs."""

    def __init__(self, stage: LifecycleStage, llm_type: str = "gemma", model_name: str = None):
        self.reporter = QualityReporter()
        self.verifier = VerificationRunner(self.reporter.report_dir)
        self.ingestion = IngestionManager()
        self.analyzer = StaticAnalyzer()
        self.normalizer = LifecycleNormalizer()
        self.prompter = PromptConstructor()
        self.stage = stage

        if llm_type == "openai":
            self.llm = OpenAIClient(model_name or "gpt-4o-mini")
        elif llm_type == "anthropic":
            self.llm = AnthropicClient(model_name or "claude-3-5-sonnet-20240620")
        else:
            self.llm = GemmaClient(model_name or "gemma2")

    def execute_analysis(self, source_path: str):
        print(f"🧐 Ingesting source: {source_path}")
        units = self.ingestion.collect(source_path)

        print(f"📊 Running Static Analysis (Stage 2)...")
        static_reports = self.analyzer.analyze(units)
        self.reporter.save_static_report(static_reports)

        final_results = []
        for unit, report in zip(units, static_reports):
            status = self.normalizer.evaluate(report["metrics"], self.stage)
            filename = unit.original_path.name
            signatures = get_code_signatures(unit.source)

            # Stage 3: RL-Verification Loop
            print(f"🤖 Requesting verification for {filename}...")
            bundle = EvidenceBundle(
                source_code=unit.source, cell_index=unit.cell_index,
                metrics=report["metrics"], static_issues=report["issues"],
                lifecycle_status=status, file_name=filename
            )

            prompt = self.prompter.build_verification_prompt(bundle, signatures)
            generated_test = self.llm.generate_test(self.prompter.SYSTEM_PROMPT, prompt)

            v_result = self.verifier.run_test(generated_test, unit.source, unit.original_path, unit.cell_index)

            # Save the full execution log for audit
            self._save_verification_log(filename, unit.cell_index, v_result)

            # Synchronized data structure to match run_qallm.py requirements
            final_results.append({
                "cell": unit.cell_index,
                "lifecycle_status": status,
                "verification": {
                    "success": v_result.success,
                    "is_broken_test": v_result.is_broken_test,
                    "coverage": v_result.coverage
                }
            })

        return final_results

    def _save_verification_log(self, filename: str, cell_idx: int, result: VerificationResult):
        """Saves raw pytest output to the session report directory."""
        log_file = self.reporter.report_dir / f"test_report_{filename}_c{cell_idx}.log"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"VERIFICATION LOG: {filename} (Cell {cell_idx})\n")
            f.write(f"PASSED: {result.success} | BROKEN: {result.is_broken_test}\n")
            f.write("-" * 50 + "\nSTDOUT:\n" + result.stdout + "\n")
            f.write("-" * 50 + "\nSTDERR:\n" + result.stderr + "\n")