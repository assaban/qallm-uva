import pytest
import shutil
from pathlib import Path
from qallm.utils.reporter import QualityReporter


def test_reporter_creates_directory_and_file(tmp_path):
    # Use tmp_path to keep tests clean
    reporter = QualityReporter(base_dir=str(tmp_path))
    sample_data = [{"cell_index": 0, "metrics": {"mi": 100}}]

    report_path = reporter.save_static_report(sample_data)

    assert report_path.exists()
    assert report_path.name == "static_analysis.json"