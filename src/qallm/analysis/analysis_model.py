from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List

from qallm.common.model import CodeUnit


@dataclass
class Finding:
    """Unified representation of a static analysis finding."""
    tool: str
    type: str  # e.g., SECURITY, COMPLEXITY, LINT
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    file: str
    line: int
    message: str
    rule_id: str
    code_snippet: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RawToolResult:
    """Standardized container for raw output from any static analysis tool."""
    tool: str
    exit_code: int
    stdout: str
    stderr: str
    artifact: str | None = None


@dataclass
class AnalysedCodeUnit:
    code_unit: CodeUnit
    findings: List[Finding] = field(default_factory=list)
    raw_tool_results: List[RawToolResult] = field(default_factory=list)
