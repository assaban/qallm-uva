"""Tests for the per-round bug-detail summariser in the improvement endpoint."""

from qallm.api.routers.results import _summarise_bug_detail


def _session(function, tests, **execution):
    details = [{"name": n, "status": s, "message": m} for (n, s, m) in tests]
    passed = sum(1 for _, s, _ in tests if s == "passed")
    failed = sum(1 for _, s, _ in tests if s == "failed")
    errors = sum(1 for _, s, _ in tests if s == "error")
    base = {"passed": passed, "failed": failed, "errors": errors,
            "skipped": 0, "total": len(tests), "coverage_percent": 80.0,
            "test_details": details}
    base.update(execution)
    return {"function": function, "rounds": [{"execution": base}]}


def test_empty_verification_returns_empty():
    assert _summarise_bug_detail(None) == []
    assert _summarise_bug_detail([]) == []


def test_failing_test_is_a_bug():
    v = [_session("divide", [
        ("test_ok", "passed", None),
        ("test_zero", "failed", "ZeroDivisionError: division by zero"),
    ])]
    out = _summarise_bug_detail(v)
    assert len(out) == 1
    fn = out[0]
    assert fn["function"] == "divide"
    assert fn["failed"] == 1
    assert len(fn["bug_tests"]) == 1
    assert fn["bug_tests"][0]["name"] == "test_zero"
    assert "ZeroDivisionError" in fn["bug_tests"][0]["message"]
    # all_tests retains the passing one too.
    assert len(fn["all_tests"]) == 2


def test_errors_are_not_counted_as_bugs():
    v = [_session("f", [
        ("test_a", "error", "ImportError"),
        ("test_b", "passed", None),
    ])]
    fn = _summarise_bug_detail(v)[0]
    assert fn["errors"] == 1
    assert fn["bug_tests"] == []  # errors are not bugs


def test_uses_final_round():
    v = [{
        "function": "g",
        "rounds": [
            {"execution": {"passed": 1, "failed": 0, "errors": 0, "skipped": 0,
                           "total": 1, "test_details": [
                               {"name": "t1", "status": "passed", "message": None}]}},
            {"execution": {"passed": 1, "failed": 1, "errors": 0, "skipped": 0,
                           "total": 2, "test_details": [
                               {"name": "t1", "status": "passed", "message": None},
                               {"name": "t2", "status": "failed", "message": "boom"}]}},
        ],
    }]
    fn = _summarise_bug_detail(v)[0]
    assert fn["failed"] == 1  # from the LAST round
    assert len(fn["all_tests"]) == 2
