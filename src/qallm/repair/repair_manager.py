"""Repair orchestration: coordinates finding grouping, repair, validation, and impact analysis.

Flow:
  1. Group findings by file
  2. For each file: build RepairRequest, call agent.repair()
  3. Validate compile (agent handles this + retry)
  4. Generate unified diff
  5. Optionally re-analyze to compute RepairImpact
  6. Persist artifacts (original, repaired, diff)
"""

from __future__ import annotations

import ast
import difflib
import json
import logging
from pathlib import Path

from qallm.analysis.analysis_model import AnalysedCodeUnit
from qallm.analysis.analysis_manager import AnalysisManager
from qallm.repair.repair_model import RepairRequest, RepairResult, RepairImpact, RepairAgent, RepairedCodeUnit

logger = logging.getLogger(__name__)


class RepairManager:
    """Coordinates the grouping of findings and the repair lifecycle."""

    def __init__(self, repair_agent: RepairAgent, analyzer: AnalysisManager):
        self.repair_agent = repair_agent
        self.analyzer = analyzer

    def repair_code_unit(
        self,
        analysed_code_unit: AnalysedCodeUnit,
        persist_dir: Path | None = None
    ) -> RepairedCodeUnit:
        """Uses Repair agents to repair the supplied code and results in RepairedCodeUnit instance.
        The repaired code might or might not compile!"""

        logger.info(f"Repairing: ({len(analysed_code_unit.findings)}) findings ["
                    f"File name: {analysed_code_unit.code_unit.original_path}")

        code_unit = analysed_code_unit.code_unit
        code_unit_path = str(code_unit.original_path.absolute())

        request = RepairRequest(
            file_path=code_unit_path,
            original_source=code_unit.source_code,
            current_findings=analysed_code_unit.findings,
        )

        repair_result = self.repair_agent.repair(request)

        # Generate diff
        repair_result.unified_diff = self._make_diff(code_unit.source_code, repair_result.repaired_source, code_unit_path)

        # Persist artifacts if a directory is provided
        if persist_dir:
            self._persist_artifacts(persist_dir, code_unit_path, code_unit.source_code, repair_result)

        repaired_code_unit = RepairedCodeUnit(analysed_code_unit, repair_result)

        logger.info("Repair completed:")

        # Log whether the repair compiles or not.
        if not repaired_code_unit.repaired_result.compiles:
            logger.error(f"Repair for {repaired_code_unit.original_code_unit.original_path}: ❌ FAILED (Could not compile)")
        else:
            logger.info(f"Repair for {repaired_code_unit.original_code_unit.original_path}: ✅ CLEAN (Compiles)")

        return repaired_code_unit

    def analyse_impact(self, repaired_code_unit: RepairedCodeUnit) -> RepairImpact | None:
        """Quantify the quality delta by re-analyzing the repaired code."""

        if not repaired_code_unit.repaired_result.compiles:
            return None

        re_analysed_code_unit = self.analyzer.analyse_code_unit(repaired_code_unit.repaired_code_unit)

        original_findings = repaired_code_unit.analysed_code.findings
        new_findings = re_analysed_code_unit.findings

        # new_findings = self.analyzer.analyze([unit])

        old_ids = {f.rule_id for f in original_findings}
        new_ids = {f.rule_id for f in new_findings}

        resolved = sorted(list(old_ids - new_ids))
        introduced = sorted(list(new_ids - old_ids))

        return RepairImpact(
            file_path=str(repaired_code_unit.analysed_code.code_unit.original_path),
            original_metrics={"finding_count": len(original_findings)},
            new_metrics={"finding_count": len(new_findings)},
            resolved_rule_ids=resolved,
            introduced_rule_ids=introduced,
            improvement_detected=len(resolved) > len(introduced),
        )

    @staticmethod
    def _validate_syntax(code: str) -> tuple[bool, str | None]:
        """Check if the code is syntactically valid."""
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"SyntaxError at line {e.lineno}: {e.msg}"

    @staticmethod
    def _make_diff(original: str, repaired: str, filename: str) -> str:
        """Generate a unified diff between original and repaired code."""
        orig_lines = original.splitlines(keepends=True)
        fix_lines = repaired.splitlines(keepends=True)
        fromfile, tofile = RepairManager._construct_artifacts_names(filename)
        diff = difflib.unified_diff(
            orig_lines, fix_lines,
            fromfile=f"a/{fromfile}",
            tofile=f"b/{tofile}",
        )
        return "".join(diff)

    @staticmethod
    def _construct_artifacts_names(code_unit_file_path:str) -> tuple[str, str]:
        stem = Path(code_unit_file_path).stem
        fromfile = f"{stem}_original.py"
        tofile = f"{stem}_repaired.py"
        return fromfile, tofile

    @staticmethod
    def _persist_artifacts(persist_dir: Path, code_unit_file_path: str, original_source_code: str, result: RepairResult) -> None:
        """Save original, repaired, and diff files for audit trail."""
        repairs_dir = persist_dir / "repairs"
        repairs_dir.mkdir(parents=True, exist_ok=True)

        fromfile, tofile = RepairManager._construct_artifacts_names(code_unit_file_path)

        (repairs_dir / Path(fromfile).name).write_text(original_source_code, encoding="utf-8")
        (repairs_dir / Path(tofile).name).write_text(result.repaired_source, encoding="utf-8")

        path_stem = Path(code_unit_file_path).stem
        if result.unified_diff:
            (repairs_dir / f"{path_stem}.diff").write_text(result.unified_diff, encoding="utf-8")

        # Save repair metadata
        meta = {
            "raw_file": code_unit_file_path,
            "from_file": fromfile,
            "repaired_file": tofile,
            "compiles": result.compiles,
            "validation_error": result.validation_error,
            "explanation": result.explanation,
        }
        (repairs_dir / f"{path_stem}_meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )