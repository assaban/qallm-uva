import pytest
from qallm.utils.reporter import QualityReporter


def test_reporter_creates_directory_and_file():
    r = QualityReporter()
    path = r.save_static_report([{"test": True}])
    assert path.exists()