from __future__ import annotations

import tempfile
import logging
from pathlib import Path
from typing import List

from qallm.analysis.analysis_model import Finding, AnalysedCodeUnit, RawToolResult
from qallm.analysis.base_analyzer import StaticCodeAnalyzer
from qallm.common.model import CodeUnit

# Tool Imports
from qallm.analysis.bandit_analyzer import BanditAnalyzer
from qallm.analysis.radon_analyzer import RadonAnalyzer

logger = logging.getLogger(__name__)

class AnalysisManager:
    """
    Stage 2 Runner.
    Coordinates Analyzers (Execution) and Normalizers (Parsing).
    """

    def __init__(self, selected_tools: List[str] | None = None):
        # Simplified: Just a list of instances, no separate registry class needed
        self.available_analyzers: List[StaticCodeAnalyzer] = [
            BanditAnalyzer(),
            RadonAnalyzer()
        ]
        self.selected_tool_names = selected_tools
        logger.info(f"Initialization completed. Selected tools: {self.selected_tool_names}")

    def _get_active_analyzers(self) -> List[StaticCodeAnalyzer]:
        """Filters analyzers based on initialization parameters."""
        if not self.selected_tool_names:
            return self.available_analyzers

        # Case-insensitive matching
        selected_lower = [t.lower() for t in self.selected_tool_names]
        return [
            a for a in self.available_analyzers
            if a.tool_name().lower() in selected_lower
        ]

    def analyse_code_unit(self, unit: CodeUnit) -> AnalysedCodeUnit:
        """Runs analysis on units and returns a unified list of Findings."""
        logger.info(f"Analyzing {unit.original_path.name}")
        analyzers = self._get_active_analyzers()
        findings: List[Finding] = []
        raw_tool_results: List[RawToolResult] = []

        # Workspace for tools that require physical files (like Bandit or Ruff)
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            reports_dir = workspace / "reports"
            reports_dir.mkdir(exist_ok=True)

            # Materialize the code unit
            filename = unit.original_path.name if unit.original_path else "cell.py"
            target_file = workspace / filename
            target_file.write_text(unit.source_code, encoding="utf-8")

            # Run each active analyzer
            for analyzer in analyzers:
                raw_res = analyzer.analyze(unit)
                raw_tool_results.append(raw_res)
                normalizer = analyzer.get_normalizer()

                if normalizer:
                    normalizer_findings = normalizer.normalize(raw_res)
                    findings.extend(normalizer_findings)

        analysed_code_unit = AnalysedCodeUnit(unit, findings, raw_tool_results)
        logger.info(f"Analyzing {unit.original_path.name} completed! Identified {len(findings)} findings.")
        return analysed_code_unit

    def analyze(self, units: List[CodeUnit]) -> List[Finding]:
        """Runs analysis on units and returns a unified list of Findings."""
        logger.info(f"Analyzing {len(units)} units")
        all_findings: List[Finding] = []
        for unit in units:
            all_findings.extend(self.analyse_code_unit(unit))
        logger.info(f"Analyzing {len(all_findings)} findings completed!")
        return all_findings