"""Generated-test-quality metric: incoherent-oracle drops surfaced for MD-002."""

from qallm.verification.models import GeneratedTest
from qallm.metrics_export import build_session_metrics, CSV_COLUMNS


def test_generated_test_carries_incoherent_separately():
    gt = GeneratedTest(
        function_name="f", oracle="correctness", test_code="x",
        is_valid=True, discarded_tests=["fixture_one", "inc_one"],
        incoherent_oracle_tests=["inc_one"],
    )
    # discarded_tests is the union; incoherent is the subset that backs MD-002.
    assert "inc_one" in gt.incoherent_oracle_tests
    assert gt.incoherent_oracle_tests == ["inc_one"]


def test_metric_reads_incoherent_count_from_summary():
    summary = {"model": "m", "oracle": "correctness",
               "incoherent_oracles_dropped": 4, "functions_verified": 3}
    m = build_session_metrics("s", summary, [], {})
    assert m.incoherent_oracles_dropped == 4
    assert m.to_dict()["incoherent_oracles_dropped"] == 4


def test_incoherent_count_is_a_csv_column():
    assert "incoherent_oracles_dropped" in CSV_COLUMNS


def test_metric_defaults_to_zero_when_absent():
    summary = {"model": "m", "oracle": "crash"}
    m = build_session_metrics("s", summary, [], {})
    assert m.incoherent_oracles_dropped == 0
