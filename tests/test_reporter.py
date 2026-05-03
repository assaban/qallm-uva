import pytest
from qallm.utils.reporter import QualityReporter


def test_reporter_creates_directory():
    r = QualityReporter()
    assert r.report_dir.exists()


def test_reporter_saves_static_report():
    r = QualityReporter()
    r.save_static_report([{"test": True}])
    path = r.report_dir / "static_analysis.json"
    assert path.exists()