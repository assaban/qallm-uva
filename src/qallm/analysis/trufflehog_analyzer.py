from __future__ import annotations
import shutil
import subprocess
import json
import tempfile
from pathlib import Path
from typing import Dict, Any
from .base_analyzer import StaticCodeAnalyzer
from .analysis_model import RawToolResult
from ..common.model import CodeUnit


class TruffleHogAnalyzer(StaticCodeAnalyzer):
    """Secret scanning strategy using TruffleHog."""

    def tool_name(self) -> str:
        return "trufflehog"

    def get_normalizer(self):
        # No dedicated normalizer; findings are mapped by map_result_to_report.
        # Implemented so the class satisfies the StaticCodeAnalyzer ABC and can
        # be instantiated (it previously could not, an abstract method was
        # missing), matching how RuffAnalyzer leaves its normalizer unset.
        return None

    def analyze(self, unit: CodeUnit) -> RawToolResult:
        """
        Executes TruffleHog by writing the code unit to a temporary directory
        and performing a filesystem scan.
        """
        if shutil.which("trufflehog") is None:
            return RawToolResult("trufflehog", 127, "", "trufflehog not installed")

        # TruffleHog typically scans files or directories.
        # We create a temporary isolated workspace for the code unit.
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            # Use original filename if available, otherwise default to source.py
            filename = unit.original_path.name if unit.original_path else "source.py"
            target_file = workspace / filename
            target_file.write_text(unit.source_code, encoding="utf-8")

            # Execute trufflehog on the temporary directory
            # --json: Outputs findings as JSON lines (one object per finding)
            # --no-update: Skips checking for tool updates (standard for automated runs)
            process = subprocess.run(
                ["trufflehog", "filesystem", str(workspace), "--json", "--no-update"],
                capture_output=True,
                text=True
            )

            stdout = process.stdout
            stderr = process.stderr
            exit_code = process.returncode

        return RawToolResult(
            tool=self.tool_name(),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            artifact=unit.original_path.name
        )

    def map_result_to_report(self, report: Dict[str, Any], raw_result: RawToolResult):
        """
        Adapter logic: Maps TruffleHog JSONL findings to the unified QALLM issues list.
        """
        if not raw_result.stdout.strip():
            return

        try:
            # TruffleHog outputs findings line-by-line (JSONL format)
            for line in raw_result.stdout.splitlines():
                if not line.strip():
                    continue

                finding = json.loads(line)

                # TruffleHog schema: extract detector name and partial secret for context
                detector = finding.get("DetectorName", "Unknown Detector")
                raw_snippet = finding.get("Raw", "")

                # Attempt to extract line number from metadata
                meta = finding.get("SourceMetadata", {}).get("Data", {}).get("Filesystem", {})
                line_no = meta.get("line", 0)

                report["issues"].append({
                    "test_id": "SECRET_EXPOSED",
                    "issue_text": f"Potential secret exposed ({detector}). Snippet: {raw_snippet[:15]}...",
                    "line_number": line_no,
                    "severity": "HIGH",
                    "confidence": "HIGH",
                    "tool": "trufflehog"
                })
        except (json.JSONDecodeError, KeyError):
            # Gracefully ignore parsing errors from individual lines
            pass