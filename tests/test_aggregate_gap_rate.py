"""Regression tests for the aggregate roll-up (E2 final surfaced both bugs).

Bug 1: AggregateMetrics.verification_gap_rate divided execution-only defects
by (confirmed findings + execution-only), which degenerates to 1.0 whenever
confirmed findings are zero, the normal case since the static analysers emit
no reliability findings (MD-006). The correct denominator is the number of
functions execution actually verified.

Bug 2: _metrics_from_dict (the resume re-read path) dropped confirmed_static
and confirmed_reliability_gap, so any resumed run reported zeros for the
RQ2 split while total_confirmed was correct.
"""

from qallm.experiments.gap_runner import _metrics_from_dict
from qallm.metrics_export import SessionMetrics, aggregate_sessions


def _session(**kw) -> SessionMetrics:
    base = dict(
        session_id="s", model="m", testgen_model="m", oracle="correctness",
        rounds=5, units_analyzed=10, functions_verified=0, cost_usd=0.0,
        tokens=0, static_findings=0, confirmed_findings=0,
        execution_only_bugs=0,
    )
    base.update(kw)
    return SessionMetrics(**base)


def test_gap_rate_uses_functions_verified_as_denominator():
    sessions = [
        _session(functions_verified=8, execution_only_bugs=2),
        _session(functions_verified=12, execution_only_bugs=2),
    ]
    agg = aggregate_sessions(sessions)
    assert agg.total_functions_verified == 20
    assert agg.verification_gap_rate == 4 / 20


def test_gap_rate_not_degenerate_when_confirmed_findings_zero():
    # The E2 shape: gaps exist, confirmed (static) findings are all zero.
    sessions = [_session(functions_verified=5, execution_only_bugs=1,
                         confirmed_findings=0)]
    agg = aggregate_sessions(sessions)
    assert agg.verification_gap_rate == 1 / 5  # not 1.0


def test_gap_ci_pairs_match_rate_definition():
    sessions = [_session(functions_verified=7, execution_only_bugs=3)]
    agg = aggregate_sessions(sessions)
    assert agg._gap_pairs == [(3, 7)]


def test_metrics_from_dict_round_trips_confirmed_split():
    row = _session(functions_verified=4, execution_only_bugs=1).to_dict()
    row["confirmed"] = 3
    row["confirmed_static"] = 1
    row["confirmed_reliability_gap"] = 2
    m = _metrics_from_dict(row)
    assert m.confirmed == 3
    assert m.confirmed_static == 1
    assert m.confirmed_reliability_gap == 2
    agg = aggregate_sessions([m])
    assert agg.total_confirmed_static == 1
    assert agg.total_confirmed_reliability_gap == 2


def test_aggregate_dict_exposes_functions_verified():
    agg = aggregate_sessions([_session(functions_verified=9)])
    assert agg.to_dict()["total_functions_verified"] == 9
