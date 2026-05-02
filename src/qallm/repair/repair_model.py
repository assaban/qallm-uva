from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from qallm.analysis.analysis_model import Finding

@dataclass
class RepairRequest:
    """A bundle of findings grouped by the file they target."""
    file_path: str
    original_source: str
    current_findings: List[Finding]
    previous_findings: List[Finding] = field(default_factory=list)
    context_metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RepairResult:
    """The outcome of an individual agent's attempt to fix a file."""
    file_path: str
    repaired_source: str
    explanation: str
    compiles: bool = False
    validation_error: Optional[str] = None

@dataclass
class RepairImpact:
    """The delta in quality metrics after a repair."""
    file_path: str
    original_metrics: Dict[str, Any]
    new_metrics: Dict[str, Any]
    resolved_rule_ids: List[str]
    introduced_rule_ids: List[str]
    improvement_detected: bool