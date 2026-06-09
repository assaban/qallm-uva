from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from qallm.analysis.analysis_model import Finding, AnalysedCodeUnit
from qallm.common.model import CodeUnit


@dataclass
class RepairedCodeUnit():
    """The outcome of an individual agent's attempt to fix a file."""
    analysed_code: AnalysedCodeUnit
    repaired_result: RepairResult

    original_code_unit: CodeUnit
    repaired_code_unit : CodeUnit

    def __init__(self, analysis_result: AnalysedCodeUnit, repaired_result: RepairResult):
        super().__init__()
        self.analysed_code = analysis_result
        self.repaired_result = repaired_result
        self.original_code_unit = analysis_result.code_unit
        self.repaired_code_unit = CodeUnit(
            source_code=repaired_result.repaired_source,
            original_path=analysis_result.code_unit.original_path,
            cell_index=self.original_code_unit.cell_index
        )



@dataclass
class VerificationFailure:
    """Evidence of a runtime defect found by verification, not static analysis.

    A logical flaw can pass every static analyser yet fail at execution. This
    carries the failing test so repair can target the flaw even when there is
    no static finding for it, the verification gap made actionable.
    """
    function_name: str
    failing_test: str
    error_excerpt: str = ""


@dataclass
class RepairRequest:
    """A bundle of findings grouped by the file they target."""
    file_path: str
    original_source: str
    current_findings: List[Finding]
    previous_findings: List[Finding] = field(default_factory=list)
    context_metadata: Dict[str, Any] = field(default_factory=dict)
    # Runtime defects found by verification (logical flaws with no static
    # finding). When present, repair acts on these too, not only findings.
    verification_failures: List["VerificationFailure"] = field(default_factory=list)

@dataclass
class RepairResult:
    """The outcome of an individual agent's attempt to fix a file."""
    file_path: str
    repaired_source: str
    explanation: str
    compiles: bool = False
    validation_error: Optional[str] = None
    unified_diff: str = ""

@dataclass
class RepairImpact:
    """The delta in quality metrics after a repair."""
    file_path: str
    original_metrics: Dict[str, Any]
    new_metrics: Dict[str, Any]
    resolved_rule_ids: List[str]
    introduced_rule_ids: List[str]
    improvement_detected: bool


class RepairAgent(ABC):
    """Abstract base for LLM-based repair engines."""

    @abstractmethod
    def repair(self, request: RepairRequest) -> RepairResult: ...
