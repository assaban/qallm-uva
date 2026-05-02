from __future__ import annotations
import shutil
import subprocess
import json
import tempfile
from pathlib import Path
from typing import Dict, Any
from .base_analyzer import StaticCodeAnalyzer
from .analysis_model import RawToolResult
from qallm.ingestion.parsers import CodeUnit


class RuffAnalyzer(StaticCodeAnalyzer):
    """Linting and security strategy using Ruff."""

    def tool_name(self) -> str:
        return "ruff"

    def analyze(self, unit: CodeUnit) -> RawToolResult:
        if shutil.which("ruff") is None:
            return RawToolResult("ruff", 127, "", "ruff not installed")

        # Ruff requires a physical file to analyze effectively
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tmp:
            tmp.write(unit.source)
            tmp_path = tmp.name

        try:
            process = subprocess.run(
                ["ruff", "check", tmp_path, "--output-format", "json"],
                capture_output=True,
                text=True
            )
            stdout = process.stdout
            stderr = process.stderr
            exit_code = process.returncode
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return RawToolResult(
            tool=self.tool_name(),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            artifact=unit.original_path.name
        )

    def map_result_to_report(self, report: Dict[str, Any], raw_result: RawToolResult):
        """Maps Ruff findings to the unified issues list."""
        try:
            data = json.loads(raw_result.stdout)
            # Ruff output is a list of findings
            for finding in data:
                report["issues"].append({
                    "test_id": finding.get("code"),
                    "issue_text": finding.get("message"),
                    "line_number": finding.get("location", {}).get("row"),
                    "severity": "LOW", # Ruff doesn't provide severity in basic json
                    "tool": self.tool_name(),
                })
        except json.JSONDecodeError:
            pass