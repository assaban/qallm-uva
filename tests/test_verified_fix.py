"""Tests for the verified-fix loop: proving a confirmed finding is fixed."""

from qallm.verification.verified_fix import (
    verify_fixes,
    VerifiedFixReport,
    FixResult,
    _defect_gone,
)


# ── type-aware before/after classification (no execution) ──

def test_reliability_now_passing_is_verified_fixed():
    v, _ = _defect_gone("RELIABILITY", passed=2, failed=0, errors=0)
    assert v == "verified_fixed"


def test_reliability_still_failing_is_not_fixed():
    v, _ = _defect_gone("RELIABILITY", passed=0, failed=1, errors=0)
    assert v == "not_fixed"


def test_security_now_failing_is_verified_fixed():
    # Exploit test no longer demonstrates the unsafe effect -> fixed.
    v, _ = _defect_gone("SECURITY", passed=0, failed=1, errors=0)
    assert v == "verified_fixed"


def test_security_still_passing_is_not_fixed():
    v, _ = _defect_gone("SECURITY", passed=1, failed=0, errors=0)
    assert v == "not_fixed"


def test_errored_on_repaired_is_inconclusive():
    v, _ = _defect_gone("RELIABILITY", passed=0, failed=0, errors=2)
    assert v == "inconclusive"


# ── end-to-end against real repaired code ──

ORIGINAL_BUG = "def add_one(x):\n    return x - 1\n"   # wrong: subtracts
REPAIRED = "def add_one(x):\n    return x + 1\n"        # correct

REPRO_TEST = (
    "def test_add_one():\n"
    "    assert add_one(3) == 4\n"   # fails on original, passes on repaired
)


def test_verified_fixed_against_repaired_source():
    confirmed = [{
        "verdict": "confirmed", "finding_index": 0, "tool": "sonar",
        "type": "RELIABILITY", "severity": "HIGH", "line": 2,
        "message": "off-by-one", "rule_id": "S1", "function": "add_one",
        "reproducing_test": REPRO_TEST,
    }]
    report = verify_fixes(confirmed, repaired_source=REPAIRED,
                          source_filename="m.py")
    assert report.verified_fixed == 1
    assert report.results[0].fix_verdict == "verified_fixed"


def test_not_fixed_when_repair_did_not_help():
    confirmed = [{
        "verdict": "confirmed", "finding_index": 0, "tool": "sonar",
        "type": "RELIABILITY", "severity": "HIGH", "line": 2,
        "message": "off-by-one", "rule_id": "S1", "function": "add_one",
        "reproducing_test": REPRO_TEST,
    }]
    # "Repaired" is still the buggy version.
    report = verify_fixes(confirmed, repaired_source=ORIGINAL_BUG,
                          source_filename="m.py")
    assert report.not_fixed == 1
    assert report.results[0].fix_verdict == "not_fixed"


def test_non_confirmed_findings_skipped():
    findings = [
        {"verdict": "refuted", "reproducing_test": None, "type": "RELIABILITY"},
        {"verdict": "not_execution_testable", "type": "COMPLEXITY"},
    ]
    report = verify_fixes(findings, repaired_source=REPAIRED)
    assert report.results == []


def test_confirmed_without_test_is_inconclusive():
    confirmed = [{
        "verdict": "confirmed", "finding_index": 0, "tool": "t",
        "type": "RELIABILITY", "severity": "HIGH", "line": 1, "message": "m",
        "rule_id": "r", "function": "f", "reproducing_test": None,
    }]
    report = verify_fixes(confirmed, repaired_source=REPAIRED)
    assert report.inconclusive == 1


def test_verified_fix_rate_excludes_inconclusive():
    report = VerifiedFixReport(results=[
        FixResult(0, "t", "RELIABILITY", "H", 1, "m", "r", "f", "verified_fixed", "x"),
        FixResult(1, "t", "RELIABILITY", "H", 2, "m", "r", "f", "not_fixed", "x"),
        FixResult(2, "t", "RELIABILITY", "H", 3, "m", "r", "f", "inconclusive", "x"),
    ])
    assert report.verified_fix_rate == 0.5  # 1 / (1 + 1)


def test_to_dict_shape():
    report = VerifiedFixReport(results=[
        FixResult(0, "sonar", "RELIABILITY", "HIGH", 2, "m", "S1", "f",
                  "verified_fixed", "proven"),
    ])
    d = report.to_dict()
    assert d["summary"]["verified_fixed"] == 1
    assert d["results"][0]["fix_verdict"] == "verified_fixed"
