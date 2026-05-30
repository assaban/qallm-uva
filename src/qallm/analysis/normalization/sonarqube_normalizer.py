"""Normalizer for SonarQube issue reports.

SonarQube's Web API returns issues with a ``type`` (BUG, VULNERABILITY,
CODE_SMELL) and a ``severity`` (BLOCKER..INFO), plus per-component
*measures* (the reliability/security/maintainability ratings). This
normalizer turns the issue list into the unified ``Finding`` shape the
rest of QALLM consumes; the ratings are carried on the RawToolResult and
read by the evaluators, not turned into findings.

SonarQube is optional. When it is not configured the analyzer never runs,
so this normalizer simply returns an empty list for an empty/blank result.
"""

from __future__ import annotations

import json

from qallm.analysis.analysis_model import Finding, RawToolResult
from qallm.analysis.normalization.base_normalizer import ToolNormalizer

# SonarQube type -> QALLM finding type.
_TYPE_MAP = {
    "BUG": "RELIABILITY",
    "VULNERABILITY": "SECURITY",
    "SECURITY_HOTSPOT": "SECURITY",
    "CODE_SMELL": "MAINTAINABILITY",
}

# SonarQube severity -> QALLM severity. SonarQube uses BLOCKER, CRITICAL,
# MAJOR, MINOR, INFO; map to the LOW/MEDIUM/HIGH/CRITICAL scale used here.
_SEVERITY_MAP = {
    "BLOCKER": "CRITICAL",
    "CRITICAL": "CRITICAL",
    "MAJOR": "HIGH",
    "MINOR": "MEDIUM",
    "INFO": "LOW",
}


class SonarQubeNormalizer(ToolNormalizer):
    tool_name = "sonarqube"

    def normalize(self, result: RawToolResult) -> list[Finding]:
        if not result or not result.stdout:
            return []
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        issues = payload.get("issues", [])
        findings: list[Finding] = []
        for issue in issues:
            sonar_type = issue.get("type", "CODE_SMELL")
            sonar_sev = issue.get("severity", "INFO")
            # component is like "projectKey:path/to/file.py"; keep the path.
            component = issue.get("component", "")
            file_path = component.split(":", 1)[-1] if ":" in component else component
            findings.append(Finding(
                tool=self.tool_name,
                type=_TYPE_MAP.get(sonar_type, "MAINTAINABILITY"),
                severity=_SEVERITY_MAP.get(sonar_sev, "LOW"),
                file=file_path or "cell.py",
                line=issue.get("line", 0) or 0,
                message=issue.get("message", ""),
                rule_id=issue.get("rule", ""),
                extra={"sonar_type": sonar_type, "sonar_severity": sonar_sev},
            ))
        return findings
