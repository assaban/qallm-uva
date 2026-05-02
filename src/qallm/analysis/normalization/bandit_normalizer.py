from __future__ import annotations
import json
from pathlib import Path
from qallm.analysis.analysis_model import Finding, RawToolResult
from .base_normalizer import ToolNormalizer
from qallm.analysis.util import get_snippet


class BanditNormalizer(ToolNormalizer):
    """
    Adapter for Bandit results.
    Maps Bandit's security JSON into unified QALLM Finding objects.
    """
    tool_name = "bandit"

    def normalize(self, raw_result: RawToolResult) -> list[Finding]:
        if not raw_result.stdout:
            return []

        try:
            data = json.loads(raw_result.stdout)
        except Exception:
            return []

        findings: list[Finding] = []
        # The artifact contains the path to the code that was analyzed
        file_path = Path(raw_result.artifact) if raw_result.artifact else None

        # Bandit results are in the 'results' array
        issues = data.get("results", [])
        for issue in issues:
            line_no = issue.get("line_number", 1)

            # Map Bandit severity (LOW, MEDIUM, HIGH) to QALLM severity
            severity = issue.get("issue_severity", "LOW").upper()

            findings.append(Finding(
                tool=self.tool_name,
                type="SECURITY",
                severity=severity,
                file=str(file_path) if file_path else "source.py",
                line=line_no,
                message=issue.get("issue_text", "Security violation detected"),
                rule_id=issue.get("test_id", "B000"),
                code_snippet=get_snippet(file_path, line_no) if file_path else None,
                extra={
                    "confidence": issue.get("issue_confidence"),
                    "cwe": issue.get("issue_cwe", {}).get("id"),
                    "more_info": issue.get("more_info")
                }
            ))

        return findings