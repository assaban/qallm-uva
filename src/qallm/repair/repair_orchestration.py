from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from pathlib import Path
import ast

from .repair_model import RepairRequest, RepairResult, RepairImpact
from qallm.analysis.analysis_model import Finding
from qallm.analysis.analysis_orchestration import AnalysisManager

class RepairAgent(ABC):
    """Abstract base for LLM-based repair engines."""
    @abstractmethod
    def repair(self, request: RepairRequest) -> RepairResult: ...

class RepairManager:
    """
    Coordinates the grouping of findings and the repair lifecycle.
    """
    def __init__(self, agent: RepairAgent, analyzer: AnalysisManager):
        self.agent = agent
        self.analyzer = analyzer

    def process_repairs(self,
                        findings: List[Finding],
                        source_code_map: Dict[str, str]) -> List[RepairResult]:
        """
        Groups findings into RepairRequests and executes repairs.
        """
        # 1. Group findings by file
        grouped: Dict[str, List[Finding]] = {}
        for f in findings:
            grouped.setdefault(f.file, []).append(f)

        results = []
        for file_path, file_findings in grouped.items():
            # Create a localized request for the specific file
            request = RepairRequest(
                file_path=file_path,
                original_source=source_code_map.get(file_path, ""),
                current_findings=file_findings
            )

            # 2. Ask the Agent to fix this specific bundle
            result = self.agent.repair(request)

            # 3. Simple Compile-Check Validation
            result.compiles, result.validation_error = self._validate_syntax(result.repaired_source)
            results.append(result)

        return results

    def _validate_syntax(self, code: str) -> tuple[bool, str | None]:
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"SyntaxError at line {e.lineno}: {e.msg}"