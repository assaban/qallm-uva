"""Tests for thesis metrics export and cross-session aggregation."""

from qallm.metrics_export import (
    build_session_metrics,
    aggregate_sessions,
    to_csv,
    CSV_COLUMNS,
    SessionMetrics,
)


def _gap_rounds():
    # One round: 2 findings, 1 confirmed at function level, 1 execution-only.
    return [{
        "round": 0,
        "findings": [
            {"status": "confirmed"}, {"status": "unconfirmed"},
        ],
        "summary": {"confirmed": 1, "unconfirmed": 1, "untested": 0,
                    "execution_only": 1, "confirmation_rate": 0.5},
    }]


def _summary():
    return {
        "model": "gemma3:4b", "testgen_model": "gemma3:4b", "oracle": "crash",
        "rounds_per_function": 3, "units_analyzed": 1, "functions_verified": 2,
        "cost": {"total_cost_usd": 0.0123, "total_tokens": 4567},
    }


def test_gap_rate_from_rounds():
    m = build_session_metrics("s1", _summary(), _gap_rounds())
    # execution_only / (confirmed_findings + execution_only) = 1 / (1 + 1)
    assert m.verification_gap_rate == 0.5
    assert m.execution_only_bugs == 1
    assert m.confirmed_findings == 1
    assert m.static_findings == 2
    # confirm/verify not run -> null, not zero.
    assert m.confirmation_rate is None
    assert m.verified_fix_rate is None
    assert m.confirmed is None


def test_metadata_carried():
    m = build_session_metrics("s1", _summary(), _gap_rounds())
    assert m.model == "gemma3:4b"
    assert m.oracle == "crash"
    assert m.rounds == 3
    assert m.cost_usd == 0.0123
    assert m.tokens == 4567


def test_confirm_and_verify_summaries_included():
    m = build_session_metrics(
        "s1", _summary(), _gap_rounds(),
        confirm_summary={"confirmed": 3, "refuted": 1, "confirmation_rate": 0.75},
        verify_summary={"verified_fixed": 2, "not_fixed": 1, "verified_fix_rate": 2/3},
    )
    assert m.confirmation_rate == 0.75
    assert m.confirmed == 3
    assert m.verified_fixed == 2
    assert round(m.verified_fix_rate, 3) == 0.667


def test_null_rate_when_no_denominator():
    # No findings, no execution-only -> gap rate is None, not 0.
    m = build_session_metrics("s1", _summary(), [])
    assert m.verification_gap_rate is None


def test_aggregate_recomputes_rates_count_weighted():
    s1 = SessionMetrics("s1", confirmed_findings=1, execution_only_bugs=1,
                        confirmed=1, refuted=1, verified_fixed=1, not_fixed=0)
    s2 = SessionMetrics("s2", confirmed_findings=3, execution_only_bugs=1,
                        confirmed=3, refuted=0, verified_fixed=2, not_fixed=2)
    agg = aggregate_sessions([s1, s2])
    assert agg.n_sessions == 2
    # gap: total_exec_only / (total_confirmed_findings + total_exec_only)
    #    = 2 / (4 + 2) = 1/3
    assert round(agg.verification_gap_rate, 3) == 0.333
    # confirmation: 4 / (4 + 1) = 0.8
    assert agg.confirmation_rate == 0.8
    # verified-fix: 3 / (3 + 2) = 0.6
    assert agg.verified_fix_rate == 0.6


def test_aggregate_empty():
    agg = aggregate_sessions([])
    assert agg.n_sessions == 0
    assert agg.verification_gap_rate is None
    assert agg.confirmation_rate is None


def test_csv_has_stable_header_and_rows():
    s1 = SessionMetrics("s1", model="m", execution_only_bugs=2)
    csv_text = to_csv([s1])
    lines = csv_text.strip().splitlines()
    assert lines[0] == ",".join(CSV_COLUMNS)
    assert "s1" in lines[1]


def test_to_dict_keys_match_csv_columns():
    s1 = SessionMetrics("s1")
    assert set(s1.to_dict().keys()) == set(CSV_COLUMNS)


def test_gap_measured_at_round_0_not_summed():
    """The verification gap is a round-0 property. Later rounds (GROW test
    noise, repair-round failures) must not be summed into the gap count.
    Regression: clean code reported false bugs from accumulated round-N tests.
    """
    gap_rounds = [
        # Round 0: the original code is clean (the true gap is 0).
        {"round": 0, "findings": [],
         "summary": {"execution_only": 0, "confirmed": 0}},
        # Later rounds: accumulated flaky tests "fail" on the (unchanged) code.
        {"round": 3, "findings": [],
         "summary": {"execution_only": 2, "confirmed": 0}},
        {"round": 5, "findings": [],
         "summary": {"execution_only": 3, "confirmed": 0}},
    ]
    m = build_session_metrics("clean", _summary(), gap_rounds)
    assert m.execution_only_bugs == 0   # round 0 only, not 0+2+3=5
    assert m.verification_gap_rate is None  # no bugs, no findings -> no gap


def test_gap_round_0_seeded_bugs_preserved():
    """A genuinely buggy original (bugs present at round 0) is still counted;
    the round-0 selection does not suppress real gap detection."""
    gap_rounds = [
        {"round": 0, "findings": [],
         "summary": {"execution_only": 5, "confirmed": 0}},
        {"round": 2, "findings": [],
         "summary": {"execution_only": 8, "confirmed": 0}},
    ]
    m = build_session_metrics("reliability", _summary(), gap_rounds)
    assert m.execution_only_bugs == 5   # the seeded bugs at round 0, not 5+8
