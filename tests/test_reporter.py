import pytest
from qallm.utils.reporter import QualityReporter


def test_reporter_creates_directory():
    r = QualityReporter()
    assert r.report_dir.exists()


def test_reporter_saves_static_report():
    from pathlib import Path
    from qallm.common.model import CodeUnit
    from qallm.analysis.analysis_model import AnalysedCodeUnit
    r = QualityReporter()
    unit = CodeUnit(source_code="x = 1", cell_index=0, original_path=Path("test.py"))
    analysed = AnalysedCodeUnit(code_unit=unit, findings=[], raw_tool_results=[])
    r.save_static_report(analysed, "round_01")
    path = r.report_dir / "round_01" / "test_static_analysis.json"
    assert path.exists()