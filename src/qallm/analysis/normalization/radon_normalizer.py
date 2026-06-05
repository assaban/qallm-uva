from __future__ import annotations
import json
from pathlib import Path

from qallm.analysis.analysis_model import Finding, RawToolResult
from .base_normalizer import ToolNormalizer
from qallm.analysis.util import get_snippet


class RadonNormalizer(ToolNormalizer):
    """
    Adapter for Radon results.
    Maps combined CC/MI JSON into unified QALLM Finding objects.
    """
    tool_name = "radon"

    def normalize(self, raw_result: RawToolResult) -> list[Finding]:
        if not raw_result.stdout:
            return []

        try:
            data = json.loads(raw_result.stdout)
        except Exception:
            return []

        findings: list[Finding] = []
        file_rel = raw_result.artifact or "source.py"

        # 1. Process Cyclomatic Complexity (CC)
        cc_blocks = data.get("complexity", [])
        for block in cc_blocks:
            cc_val = block.get("complexity", 0)
            if cc_val > 5:  # Logic check: only report significant complexity
                line = block.get("lineno", 1)
                name = block.get("name", "unknown")

                findings.append(Finding(
                    tool=self.tool_name,
                    type="COMPLEXITY",
                    severity=self._severity_from_cc(cc_val),
                    file=file_rel,
                    line=line,
                    message=f"High complexity in '{name}' (CC={cc_val})",
                    rule_id="CC",
                    code_snippet=get_snippet(Path(raw_result.artifact), line),
                    extra={"complexity": cc_val, "rank": block.get("rank")}
                ))

        # 2. Process Maintainability Index (MI)
        mi_data = data.get("maintainability", {})
        mi_score = mi_data.get("mi")
        if mi_score is not None and mi_score < 70:
            findings.append(Finding(
                tool= self.tool_name,
                type="MAINTAINABILITY",
                severity=self._severity_from_mi(mi_score),
                file=file_rel,
                line=1,
                message=f"Low maintainability index (MI={mi_score:.2f})",
                rule_id="MI",
                extra={"mi_score": mi_score, "rank": mi_data.get("rank")}
            ))

        return findings

    def _severity_from_cc(self, cc: int) -> str:
        if cc >= 20:
            return "CRITICAL"
        if cc >= 15:
            return "HIGH"
        return "MEDIUM"

    def _severity_from_mi(self, mi: float) -> str:
        if mi < 40:
            return "CRITICAL"
        if mi < 60:
            return "HIGH"
        return "MEDIUM"