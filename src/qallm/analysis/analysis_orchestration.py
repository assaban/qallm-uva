from __future__ import annotations

import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict

from qallm.analysis.analysis_model import Finding, RawToolResult
from qallm.analysis.base_analyzer import StaticCodeAnalyzer
from qallm.analysis.normalization.base_normalizer import ToolNormalizer
from qallm.ingestion.parsers import CodeUnit

# Tool Imports
from qallm.analysis.bandit_analyzer import BanditAnalyzer
from qallm.analysis.radon_analyzer import RadonAnalyzer


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

    def analyze(self, units: List[CodeUnit]) -> List[Finding]:
        """Runs analysis on units and returns a unified list of Findings."""
        all_findings: List[Finding] = []
        analyzers = self._get_active_analyzers()

        for unit in units:
            # Workspace for tools that require physical files (like Bandit or Ruff)
            with tempfile.TemporaryDirectory() as tmp_dir:
                workspace = Path(tmp_dir)
                reports_dir = workspace / "reports"
                reports_dir.mkdir(exist_ok=True)

                # Materialize the code unit
                filename = unit.original_path.name if unit.original_path else "cell.py"
                target_file = workspace / filename
                target_file.write_text(unit.source, encoding="utf-8")

                # Run each active analyzer
                for analyzer in analyzers:
                    raw_res = analyzer.analyze(unit)
                    normalizer = analyzer.get_normalizer()

                    if normalizer:
                        findings = normalizer.normalize(raw_res)
                        all_findings.extend(findings)

        return all_findings