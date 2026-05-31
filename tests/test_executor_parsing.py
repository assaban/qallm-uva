"""Tests for pytest-JSON parsing, especially error-phase message capture.

A test that errors during fixture setup (e.g. it references a fixture the
generated file never defines) lands its traceback under the "setup" phase,
not "call". The parser must surface that, otherwise the UI shows
"ERROR" with no explanation, which is exactly what was observed for the
`dangerous` function's tests.
"""

import json
from pathlib import Path

from qallm.verification.executor import _parse_pytest_json


def _write(tmp_path, data) -> Path:
    p = tmp_path / "report.json"
    p.write_text(json.dumps(data))
    return p


def test_setup_error_message_is_captured(tmp_path):
    report = {
        "tests": [{
            "nodeid": "test_generated.py::test_uses_missing_fixture",
            "outcome": "error",
            "setup": {"longrepr": "fixture 'fixed_obj' not found",
                      "duration": 0.01},
        }]
    }
    details, counts = _parse_pytest_json(_write(tmp_path, report))
    assert counts["errors"] == 1
    assert details[0].status == "error"
    assert details[0].message is not None
    assert "fixed_obj" in details[0].message
    assert details[0].message.startswith("[setup error]")


def test_call_failure_message_unchanged(tmp_path):
    report = {
        "tests": [{
            "nodeid": "test_generated.py::test_assert",
            "outcome": "failed",
            "call": {"longrepr": "assert 50 == 43", "duration": 0.02},
        }]
    }
    details, counts = _parse_pytest_json(_write(tmp_path, report))
    assert counts["failed"] == 1
    assert details[0].status == "failed"
    # Call-phase failures keep their raw message, no phase prefix.
    assert details[0].message == "assert 50 == 43"


def test_passed_test_has_no_message(tmp_path):
    report = {"tests": [{
        "nodeid": "test_generated.py::test_ok", "outcome": "passed",
        "call": {"duration": 0.01},
    }]}
    details, counts = _parse_pytest_json(_write(tmp_path, report))
    assert counts["passed"] == 1
    assert details[0].status == "passed"
    assert details[0].message is None


def test_teardown_error_is_captured(tmp_path):
    report = {"tests": [{
        "nodeid": "test_generated.py::test_td", "outcome": "error",
        "call": {"duration": 0.01},
        "teardown": {"longrepr": "boom in teardown"},
    }]}
    details, _ = _parse_pytest_json(_write(tmp_path, report))
    # call has no longrepr, so teardown is surfaced.
    assert "boom in teardown" in details[0].message
    assert details[0].message.startswith("[teardown error]")
