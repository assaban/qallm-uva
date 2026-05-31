"""Tests for type-aware confirm/refute of individual findings."""

from qallm.verification.confirm_refute import (
    FindingConfirmer,
    ConfirmRefuteReport,
    FindingVerdict,
    _classify_outcome,
)
from qallm.verification.models import FunctionInfo


def _func():
    return FunctionInfo(
        name="dangerous", source="def dangerous(x):\n    return eval(x)",
        docstring=None, args=[("x", None)], lineno=1, filepath="m.py",
    )


# ── classification logic (no LLM, no execution) ──

def test_reliability_failure_is_confirmed():
    v, _ = _classify_outcome("RELIABILITY", passed=0, failed=1, errors=0)
    assert v == "confirmed"


def test_reliability_pass_is_refuted():
    v, _ = _classify_outcome("RELIABILITY", passed=2, failed=0, errors=0)
    assert v == "refuted"


def test_security_pass_is_confirmed():
    # A security test asserts the unsafe effect occurs; passing = exploitable.
    v, _ = _classify_outcome("SECURITY", passed=1, failed=0, errors=0)
    assert v == "confirmed"


def test_security_failure_is_refuted():
    v, _ = _classify_outcome("SECURITY", passed=0, failed=1, errors=0)
    assert v == "refuted"


def test_all_errored_is_inconclusive():
    v, _ = _classify_outcome("RELIABILITY", passed=0, failed=0, errors=3)
    assert v == "inconclusive"


# ── type-awareness: complexity/maintainability never run ──

class _FakeLLM:
    def __init__(self):
        self.calls = 0
    def chat(self, system, user, tracker=None):
        self.calls += 1
        raise AssertionError("should not be called for non-testable findings")


def test_complexity_finding_not_execution_testable_no_llm_call():
    llm = _FakeLLM()
    confirmer = FindingConfirmer(llm)
    findings = [{"tool": "Radon", "type": "COMPLEXITY", "severity": "MEDIUM",
                 "line": 1, "message": "cyclomatic complexity is high",
                 "rule_id": "CC"}]
    report = confirmer.confirm_findings(
        _func(), findings, source_code="def dangerous(x):\n    return x",
    )
    assert llm.calls == 0
    assert report.not_testable == 1
    assert report.verdicts[0].verdict == "not_execution_testable"


def test_maintainability_also_not_testable():
    confirmer = FindingConfirmer(_FakeLLM())
    findings = [{"tool": "Radon", "type": "MAINTAINABILITY", "severity": "LOW",
                 "line": 1, "message": "low MI", "rule_id": "MI"}]
    report = confirmer.confirm_findings(
        _func(), findings, source_code="def dangerous(x):\n    return x",
    )
    assert report.verdicts[0].verdict == "not_execution_testable"


# ── report summary maths ──

def test_confirmation_rate_excludes_inconclusive_and_nontestable():
    report = ConfirmRefuteReport(verdicts=[
        FindingVerdict(0, "t", "RELIABILITY", "HIGH", 1, "m", "r", "f",
                       "confirmed", "x"),
        FindingVerdict(1, "t", "RELIABILITY", "HIGH", 2, "m", "r", "f",
                       "refuted", "x"),
        FindingVerdict(2, "t", "COMPLEXITY", "LOW", 3, "m", "r", "f",
                       "not_execution_testable", "x"),
        FindingVerdict(3, "t", "RELIABILITY", "HIGH", 4, "m", "r", "f",
                       "inconclusive", "x"),
    ])
    # rate = confirmed / (confirmed + refuted) = 1 / 2
    assert report.confirmation_rate == 0.5
    assert report.not_testable == 1
    assert report.inconclusive == 1


def test_to_dict_shape():
    report = ConfirmRefuteReport(verdicts=[
        FindingVerdict(0, "bandit", "SECURITY", "HIGH", 2, "eval", "B307",
                       "dangerous", "confirmed", "demo", reproducing_test="def test(): ..."),
    ])
    d = report.to_dict()
    assert d["summary"]["confirmed"] == 1
    assert d["verdicts"][0]["verdict"] == "confirmed"
    assert d["verdicts"][0]["reproducing_test"] is not None
