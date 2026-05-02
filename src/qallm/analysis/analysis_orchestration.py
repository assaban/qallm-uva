import tempfile
import uuid
from pathlib import Path
from typing import List

from qallm.analysis.analysis_model import Finding

from qallm.ingestion.parsers import CodeUnit
from qallm.analysis.analyzer_registry import AnalyzerRegistry

# Tool Imports
from qallm.analysis.bandit_analyzer import BanditAnalyzer
from qallm.analysis.radon_analyzer import RadonAnalyzer

class AnalysisOrchestrator:
    """
    Stage 2 Runner.
    Coordinates Analyzers (Execution) and Normalizers (Parsing).
    """

    def __init__(self, selected_tools: List[str] = None):
        # Initialize execution strategies
        self.analyzer_reg = AnalyzerRegistry([
            BanditAnalyzer(),
            # RadonAnalyzer()
        ])
        self.selected_tools = selected_tools

    def analyze(self, units: List[CodeUnit]) -> List[Finding]:
        all_reports = []
        all_findings = []

        for unit in units:
            with tempfile.TemporaryDirectory() as tmp_dir:
                workspace = Path(tmp_dir)
                reports_dir = workspace / "reports"
                reports_dir.mkdir()

                # 1. Prepare Workspace
                target_file = workspace / (unit.original_path.name if unit.original_path else "cell.py")
                target_file.write_text(unit.source, encoding="utf-8")

                unit_findings = []

                # 2. Execute Analyzers
                analyzers = self.analyzer_reg.pick(self.selected_tools)
                for analyzer in analyzers:
                    # Run the tool
                    raw_res = analyzer.analyze(unit)

                    # 3. Normalize Results
                    normalizer = analyzer.get_normalizer()
                    if normalizer:
                        # Convert Raw Result to Finding objects
                        # Note: we pass the artifact name which the normalizer reads from disk
                        findings = normalizer.normalize(raw_res)
                        unit_findings.extend(findings)

                # add all unit findings to list of all findings.
                all_findings.extend(unit_findings)

                # 4. Format for Orchestrator/Thesis Reporting
                all_reports.append({
                    "file_name": target_file.name,
                    "cell_index": unit.cell_index,
                    "findings": [f.__dict__ for f in unit_findings],
                    "metrics": self._summarize_metrics(unit_findings)
                })

        return all_findings

    def _summarize_metrics(self, findings: list) -> dict:
        """Helper to extract aggregate scores from normalized findings."""
        metrics = {"mi": 100.0, "cc": 1.0}
        for f in findings:
            if f.tool == "radon" and f.rule_id == "CC":
                metrics["cc"] = max(metrics["cc"], f.extra.get("complexity", 1.0))
            # You can add logic to estimate MI based on findings
        return metrics