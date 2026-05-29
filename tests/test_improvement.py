"""Tests for the improvement-log delta computation."""

from qallm.improvement import (
    APPEARED,
    IMPROVED,
    REGRESSED,
    UNCHANGED,
    build_improvement_report,
)


def _verdict(status, indicators):
    """indicators: list of (dimension, name, comparator, threshold, measured, status)."""
    by_dim: dict = {}
    for dim, name, comp, thr, meas, st in indicators:
        by_dim.setdefault(dim, []).append({
            "name": name, "evaluator": f"e.{name}", "comparator": comp,
            "threshold": thr, "measured": meas, "status": st, "detail": "",
        })
    return {
        "status": status,
        "dimensions": [
            {"dimension": d, "status": "PASS", "indicators": inds}
            for d, inds in by_dim.items()
        ],
    }


def test_status_transition_fail_to_pass_is_improvement():
    parent = _verdict("FAIL", [("Security", "bandit_high", "LE", 0, 3.0, "FAIL")])
    variant = _verdict("PASS", [("Security", "bandit_high", "LE", 0, 0.0, "PASS")])
    rep = build_improvement_report(
        round_number=1, unit_id="f.py::foo", accepted=True,
        parent_verdict=parent, variant_verdict=variant, parent_round=0,
    )
    ind = rep.dimensions[0].indicators[0]
    assert ind.direction == IMPROVED
    assert ind.status_transition == "FAIL->PASS"
    assert ind.measured_delta == -3.0


def test_pass_to_fail_is_regression():
    parent = _verdict("PASS", [("Security", "bandit_high", "LE", 0, 0.0, "PASS")])
    variant = _verdict("FAIL", [("Security", "bandit_high", "LE", 0, 2.0, "FAIL")])
    rep = build_improvement_report(
        round_number=2, unit_id="f.py::foo", accepted=False,
        parent_verdict=parent, variant_verdict=variant, parent_round=1,
    )
    assert rep.dimensions[0].indicators[0].direction == REGRESSED


def test_same_status_higher_is_better_increase_is_improvement():
    # GE comparator (e.g. test_pass_rate): higher measured is better.
    parent = _verdict("PASS", [("Reliability", "pass_rate", "GE", 0.9, 0.92, "PASS")])
    variant = _verdict("PASS", [("Reliability", "pass_rate", "GE", 0.9, 0.99, "PASS")])
    rep = build_improvement_report(
        round_number=1, unit_id="f.py::foo", accepted=True,
        parent_verdict=parent, variant_verdict=variant,
    )
    assert rep.dimensions[0].indicators[0].direction == IMPROVED


def test_unchanged_value_is_unchanged():
    parent = _verdict("PASS", [("Maintainability", "mi", "GE", 60, 75.0, "PASS")])
    variant = _verdict("PASS", [("Maintainability", "mi", "GE", 60, 75.0, "PASS")])
    rep = build_improvement_report(
        round_number=1, unit_id="f.py::foo", accepted=True,
        parent_verdict=parent, variant_verdict=variant,
    )
    assert rep.dimensions[0].indicators[0].direction == UNCHANGED


def test_indicator_appearing_in_variant_only():
    parent = _verdict("PASS", [])
    variant = _verdict("PASS", [("Security", "cwe", "LE", 0, 1.0, "FAIL")])
    rep = build_improvement_report(
        round_number=1, unit_id="f.py::foo", accepted=True,
        parent_verdict=parent, variant_verdict=variant,
    )
    assert rep.dimensions[0].indicators[0].direction == APPEARED


def test_counts_and_headline():
    parent = _verdict("FAIL", [
        ("Security", "bandit_high", "LE", 0, 3.0, "FAIL"),
        ("Maintainability", "mi", "GE", 60, 75.0, "PASS"),
    ])
    variant = _verdict("PASS", [
        ("Security", "bandit_high", "LE", 0, 0.0, "PASS"),
        ("Maintainability", "mi", "GE", 60, 75.0, "PASS"),
    ])
    rep = build_improvement_report(
        round_number=1, unit_id="f.py::foo", accepted=True,
        parent_verdict=parent, variant_verdict=variant,
        judge_verdict={"outcome": "IMPROVEMENT", "rationale": "security fixed"},
    )
    counts = rep.counts()
    assert counts[IMPROVED] == 1
    assert counts[UNCHANGED] == 1
    assert "ACCEPTED" in rep.headline()
    assert rep.judge_outcome == "IMPROVEMENT"
    assert rep.to_dict()["judge_rationale"] == "security fixed"


def test_none_parent_verdict_handled():
    # Round 1 against a baseline that has no measured values for some indicator.
    variant = _verdict("PASS", [("Security", "bandit_high", "LE", 0, 0.0, "PASS")])
    rep = build_improvement_report(
        round_number=1, unit_id="f.py::foo", accepted=True,
        parent_verdict=None, variant_verdict=variant,
    )
    # With no parent, every variant indicator is "appeared".
    assert rep.dimensions[0].indicators[0].direction == APPEARED
