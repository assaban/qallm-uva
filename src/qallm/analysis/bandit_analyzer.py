from __future__ import annotations
import shutil
import subprocess
import json
from typing import Dict, Any
from .base_analyzer import StaticCodeAnalyzer
from .models import RawToolResult
from qallm.ingestion.parsers import CodeUnit
from .normalization.bandit_normalizer import BanditNormalizer
from .normalization.base import ToolNormalizer


class BanditAnalyzer(StaticCodeAnalyzer):
    """Security analysis strategy using Bandit."""

    def __init__(self):
        super().__init__()
        self.name = "Bandit"
        self.normalizer = BanditNormalizer()

    def tool_name(self) -> str:
        return self.name

    def get_normalizer(self) -> ToolNormalizer:
        return self.normalizer

    def analyze(self, unit: CodeUnit) -> RawToolResult:
        if shutil.which("bandit") is None:
            return RawToolResult("bandit", 127, "", "bandit not installed")

        # Run bandit on stdin
        process = subprocess.run(
            ["bandit", "-r", "-f", "json", "-q", "-"],
            input=unit.source,
            capture_output=True,
            text=True
        )

        return RawToolResult(
            tool=self.tool_name(),
            exit_code=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
            artifact=unit.original_path.name
        )

    def map_result_to_report(self, report: Dict[str, Any], raw_result: RawToolResult):
        """Maps Bandit security findings to the unified issues list."""
        try:
            data = json.loads(raw_result.stdout)
            findings = data.get("results", [])

            for issue in findings:
                # Standardize keys and tag with tool name
                report["issues"].append({
                    "test_id": issue.get("test_id"),
                    "issue_text": issue.get("issue_text"),
                    "line_number": issue.get("line_number"),
                    "severity": issue.get("issue_severity"),
                    "confidence": issue.get("issue_confidence"),
                    "tool": self.tool_name(),
                })
        except json.JSONDecodeError:
            pass