"""The confirmed count splits into static and reliability-gap sources.

The full E2 run computed the split in confirm_summary but SessionMetrics dropped
it before aggregation, so aggregate.json reported only a blended total_confirmed.
That hid that the reliability-gap confirmations dominate (which is why a raw
confirmation rate is degenerate). These tests pin the split through the whole
metrics path: summary -> session -> aggregate -> CSV.
"""
from __future__ import annotations

from qallm.metrics_export import (
    CSV_COLUMNS,
    aggregate_sessions,
    build_session_metrics,
)


def _session():
    cs = {
        "confirmed": 10,
        "confirmed_static": 2,
        "confirmed_reliability_gap": 8,
        "refuted": 0,
        "confirmation_rate": 1.0,
        "inconclusive": 3,
        "not_execution_testable": 5,
    }
    return build_session_metrics(
        "s1",
        summary={"static_findings": 8, "execution_only_bugs": 10},
        gap_rounds=[],
        confirm_summary=cs,
        verify_summary={"verified_fixed": 6, "not_fixed": 4, "verified_fix_rate": 0.6},
    )


def test_session_carries_split():
    m = _session()
    assert m.confirmed == 10
    assert m.confirmed_static == 2
    assert m.confirmed_reliability_gap == 8


def test_aggregate_carries_split():
    d = aggregate_sessions([_session(), _session()]).to_dict()
    assert d["total_confirmed"] == 20
    assert d["total_confirmed_static"] == 4
    assert d["total_confirmed_reliability_gap"] == 16


def test_csv_has_split_columns():
    assert "confirmed_static" in CSV_COLUMNS
    assert "confirmed_reliability_gap" in CSV_COLUMNS


def test_absent_confirm_summary_leaves_split_none():
    m = build_session_metrics("s", summary={"static_findings": 1,
                              "execution_only_bugs": 0}, gap_rounds=[])
    assert m.confirmed_static is None
    assert m.confirmed_reliability_gap is None
