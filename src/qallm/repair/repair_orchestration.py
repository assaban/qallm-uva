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
    Coordinates the grouping of findings and the repair lifecycle.[cite: 34]
    """

    def __init__(self, agent: RepairAgent, analyzer: AnalysisManager):
        self.agent = agent
        self.analyzer = analyzer

    def process_repairs(self,
                        findings: List[Finding],
                        source_code_map: Dict[str, str]) -> List[RepairResult]:
        """
        Groups findings into RepairRequests and executes repairs.[cite: 34]
        """
        grouped: Dict[str, List[Finding]] = {}
        for f in findings:
            grouped.setdefault(f.file, []).append(f)

        results = []
        for file_path, file_findings in grouped.items():
            request = RepairRequest(
                file_path=file_path,
                original_source=source_code_map.get(file_path, ""),
                current_findings=file_findings
            )

            result = self.agent.repair(request)
            result.compiles, result.validation_error = self._validate_syntax(result.repaired_source)
            results.append(result)

        return results

    def analyze_impact(self,
                       original_findings: List[Finding],
                       repair_result: RepairResult) -> RepairImpact | None:
        """
        Quantifies the quality delta by re-analyzing the repaired code.[cite: 32]
        """
        from qallm.ingestion.parsers import CodeUnit

        if not repair_result.compiles:
            return None

        # Re-analyze the repaired string[cite: 32]
        unit = CodeUnit(
            source=repair_result.repaired_source,
            original_path=Path(repair_result.file_path),
            cell_index=0
        )

        new_findings = self.analyzer.analyze([unit])

        # Compare rule IDs to see what changed[cite: 32]
        old_ids = {f.rule_id for f in original_findings}
        new_ids = {f.rule_id for f in new_findings}

        resolved = sorted(list(old_ids - new_ids))
        introduced = sorted(list(new_ids - old_ids))

        return RepairImpact(
            file_path=repair_result.file_path,
            original_metrics={"finding_count": len(original_findings)},
            new_metrics={"finding_count": len(new_findings)},
            resolved_rule_ids=resolved,
            introduced_rule_ids=introduced,
            improvement_detected=len(resolved) > len(introduced)
        )

    def _validate_syntax(self, code: str) -> tuple[bool, str | None]:
        """Checks if the code is syntactically valid.[cite: 34]"""
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"SyntaxError at line {e.lineno}: {e.msg}"