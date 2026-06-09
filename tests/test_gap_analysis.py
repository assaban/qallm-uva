"""Tests for static-vs-execution gap correlation."""

from qallm.analysis.gap_analysis import (
    build_gap_report,
    function_spans,
    _function_for_line,
)

SOURCE = '''import os

def dangerous(user_input):
    value = eval(user_input)
    return value

def complex_branching(n):
    total = 0
    for i in range(n):
        if i % 2 == 0:
            total += 1
    return total
'''


def test_function_spans_and_line_mapping():
    spans = function_spans(SOURCE)
    names = {s.name for s in spans}
    assert names == {"dangerous", "complex_branching"}
    # Line 4 (eval) is inside dangerous; line 10 (if) inside complex_branching.
    assert _function_for_line(spans, 4) == "dangerous"
    assert _function_for_line(spans, 10) == "complex_branching"
    # A line outside any function maps to None.
    assert _function_for_line(spans, 1) is None


def _verification(func, passed, failed, errors):
    return [{
        "function": func,
        "rounds": [{"execution": {
            "passed": passed, "failed": failed, "errors": errors,
            "total": passed + failed + errors,
        }}],
    }]


def test_finding_confirmed_when_function_has_bug():
    findings = [{"tool": "bandit", "line": 4, "severity": "HIGH",
                 "message": "eval", "rule_id": "B307"}]
    verification = _verification("dangerous", passed=2, failed=1, errors=0)
    rep = build_gap_report(0, SOURCE, findings, verification)
    assert rep.confirmed == 1
    assert rep.unconfirmed == 0
    assert rep.findings[0].function == "dangerous"
    assert rep.findings[0].status == "confirmed"


def test_finding_unconfirmed_when_tested_but_no_bug():
    findings = [{"tool": "bandit", "line": 4, "severity": "HIGH",
                 "message": "eval", "rule_id": "B307"}]
    verification = _verification("dangerous", passed=3, failed=0, errors=0)
    rep = build_gap_report(0, SOURCE, findings, verification)
    assert rep.unconfirmed == 1
    assert rep.confirmed == 0
    assert rep.findings[0].status == "unconfirmed"


def test_finding_untested_when_all_errored():
    # All tests errored (the fixed_obj situation): no execution evidence.
    findings = [{"tool": "bandit", "line": 4, "severity": "HIGH",
                 "message": "eval", "rule_id": "B307"}]
    verification = _verification("dangerous", passed=0, failed=0, errors=5)
    rep = build_gap_report(0, SOURCE, findings, verification)
    assert rep.untested == 1
    assert rep.findings[0].status == "untested"


def test_execution_only_is_the_gap():
    # complex_branching has bugs but NO static finding -> the gap.
    findings = [{"tool": "bandit", "line": 4, "severity": "HIGH",
                 "message": "eval", "rule_id": "B307"}]  # only on dangerous
    verification = (
        _verification("dangerous", 2, 0, 0)
        + _verification("complex_branching", 5, 3, 0)
    )
    rep = build_gap_report(0, SOURCE, findings, verification)
    assert rep.execution_only_functions == ["complex_branching"]


def test_confirmation_rate():
    findings = [
        {"tool": "bandit", "line": 4, "severity": "HIGH", "message": "a", "rule_id": "B1"},
        {"tool": "radon", "line": 10, "severity": "LOW", "message": "b", "rule_id": "R1"},
    ]
    verification = (
        _verification("dangerous", 1, 1, 0)        # confirmed
        + _verification("complex_branching", 3, 0, 0)  # unconfirmed
    )
    rep = build_gap_report(0, SOURCE, findings, verification)
    assert rep.confirmed == 1
    assert rep.unconfirmed == 1
    assert rep.confirmation_rate == 0.5


def test_to_dict_shape():
    findings = [{"tool": "bandit", "line": 4, "severity": "HIGH",
                 "message": "eval", "rule_id": "B307"}]
    rep = build_gap_report(0, SOURCE, findings, _verification("dangerous", 1, 1, 0))
    d = rep.to_dict()
    assert d["round"] == 0
    assert d["summary"]["confirmed"] == 1
    assert "confirmation_rate" in d["summary"]
    assert d["findings"][0]["status"] == "confirmed"


def test_syntax_error_source_no_crash():
    rep = build_gap_report(0, "def broken(:\n  pass", [], None)
    assert rep.findings == []
    assert rep.execution_only_functions == []


def test_build_gap_report_accepts_finding_objects():
    """findings may be Finding dataclass objects, not just dicts.

    Regression: the in-memory metrics_only path passes analysed.findings (a
    list of Finding objects) straight to build_gap_report, which previously
    called f.get(...) and raised "'Finding' object has no attribute 'get'" on
    any unit that had static findings. Both dict and object inputs must work.
    """
    from qallm.analysis.analysis_model import Finding

    finding = Finding(
        tool="bandit", type="security", severity="HIGH", file="x.py",
        line=2, message="eval use", rule_id="B307", code_snippet="", extra={},
    )
    rep = build_gap_report(0, SOURCE, [finding], [])
    assert len(rep.findings) == 1
    assert rep.findings[0].tool == "bandit"
    assert rep.findings[0].severity == "HIGH"


def test_build_gap_report_dict_and_object_agree():
    """A dict finding and the equivalent Finding object yield the same fields."""
    from qallm.analysis.analysis_model import Finding

    obj = Finding(tool="ruff", type="style", severity="LOW", file="x.py",
                  line=2, message="m", rule_id="E501", code_snippet="", extra={})
    as_dict = {"tool": "ruff", "severity": "LOW", "line": 2, "message": "m", "rule_id": "E501"}
    r_obj = build_gap_report(0, SOURCE, [obj], [])
    r_dict = build_gap_report(0, SOURCE, [as_dict], [])
    assert r_obj.findings[0].tool == r_dict.findings[0].tool
    assert r_obj.findings[0].line == r_dict.findings[0].line
