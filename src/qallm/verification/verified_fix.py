"""Verify that a repair actually fixed a confirmed finding, by execution.

The strategy doc's principle is "prove the fix, do not assert it". Static
tools and even LLM repairers typically *claim* a fix is correct. QALLM can
do better: when a finding was confirmed by a reproducing test (the test
demonstrated the defect against the original code), re-run that same test
against the repaired code and see whether the defect is gone.

This is the verified-fix loop. For a confirmed finding it yields:

* verified_fixed: the reproducing test demonstrated the defect on the
  original code and shows it is gone on the repaired code. A proven fix.
* not_fixed: the test still demonstrates the defect on the repaired code;
  the repair did not address it.
* inconclusive: the test errored on the repaired code, or the finding was
  not actually confirmed on the original (no reproducing test to re-run),
  so there is no clean before/after to compare.

The "is the defect gone" check is type-aware, mirroring confirm/refute but
inverted for the repaired code:

* RELIABILITY: the reproducing test asserts CORRECT behaviour, so on the
  original it FAILED (bug present). Fixed means it now PASSES on repaired.
* SECURITY: the reproducing test asserts the unsafe effect OCCURS, so on
  the original it PASSED (exploitable). Fixed means it now FAILS on
  repaired (the unsafe effect no longer occurs).

The verified-fix rate is verified_fixed over the confirmed findings we were
able to re-test (verified_fixed + not_fixed), so it is not deflated by
findings that could not be re-run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from qallm.verification.confirm_refute import _RELIABILITY_TYPES
from qallm.verification.executor import run_tests

logger = logging.getLogger(__name__)

FixVerdict = Literal["verified_fixed", "not_fixed", "inconclusive"]


@dataclass
class FixResult:
    finding_index: int
    tool: str
    type: str
    severity: str
    line: int
    message: str
    rule_id: str
    function: str | None
    fix_verdict: FixVerdict
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_index": self.finding_index,
            "tool": self.tool, "type": self.type, "severity": self.severity,
            "line": self.line, "message": self.message,
            "rule_id": self.rule_id, "function": self.function,
            "fix_verdict": self.fix_verdict, "reason": self.reason,
        }


@dataclass
class VerifiedFixReport:
    results: list[FixResult] = field(default_factory=list)

    @property
    def verified_fixed(self) -> int:
        return sum(1 for r in self.results if r.fix_verdict == "verified_fixed")

    @property
    def not_fixed(self) -> int:
        return sum(1 for r in self.results if r.fix_verdict == "not_fixed")

    @property
    def inconclusive(self) -> int:
        return sum(1 for r in self.results if r.fix_verdict == "inconclusive")

    @property
    def verified_fix_rate(self) -> float | None:
        """verified_fixed over the findings we could re-test (verified_fixed
        + not_fixed). None when nothing was re-testable."""
        denom = self.verified_fixed + self.not_fixed
        return (self.verified_fixed / denom) if denom else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "summary": {
                "verified_fixed": self.verified_fixed,
                "not_fixed": self.not_fixed,
                "inconclusive": self.inconclusive,
                "verified_fix_rate": self.verified_fix_rate,
            },
        }


def _defect_gone(ftype: str, passed: int, failed: int, errors: int) -> tuple[FixVerdict, str]:
    """Did the reproducing test show the defect is gone on repaired code?"""
    if errors > 0 and passed == 0 and failed == 0:
        return "inconclusive", (
            "The reproducing test errored against the repaired code, so the "
            "fix could not be verified by execution."
        )
    if ftype in _RELIABILITY_TYPES:
        # Reproducing test asserts correct behaviour: passing on repaired
        # means the bug is gone.
        if passed > 0 and failed == 0:
            return "verified_fixed", (
                "The reproducing test, which failed against the original "
                "code, now passes against the repaired code: the bug is "
                "provably gone."
            )
        if failed > 0:
            return "not_fixed", (
                "The reproducing test still fails against the repaired code; "
                "the repair did not fix the defect."
            )
        return "inconclusive", "No clear result against the repaired code."
    # SECURITY: reproducing test asserts the unsafe effect occurs. Fixed
    # means it no longer can, i.e. the test now fails.
    if failed > 0 and passed == 0:
        return "verified_fixed", (
            "The exploit test, which passed against the original code, now "
            "fails against the repaired code: the unsafe behaviour is no "
            "longer reachable."
        )
    if passed > 0:
        return "not_fixed", (
            "The exploit test still passes against the repaired code; the "
            "vulnerability is still reachable."
        )
    return "inconclusive", "No clear result against the repaired code."


def verify_fixes(
    confirmed_findings: list[dict],
    repaired_source: str,
    source_filename: str = "source_module.py",
    source_origin=None,
) -> VerifiedFixReport:
    """Re-run each confirmed finding's reproducing test against repaired code.

    ``confirmed_findings`` are verdict dicts from confirm/refute with
    ``verdict == "confirmed"`` and a ``reproducing_test``. Findings without a
    reproducing test are skipped (nothing to re-run).
    """
    report = VerifiedFixReport()
    for finding in confirmed_findings:
        if finding.get("verdict") != "confirmed":
            continue
        test_code = finding.get("reproducing_test")
        base = dict(
            finding_index=finding.get("finding_index", -1),
            tool=finding.get("tool", "?"),
            type=(finding.get("type") or "?").upper(),
            severity=finding.get("severity", "?"),
            line=int(finding.get("line", 0) or 0),
            message=finding.get("message", ""),
            rule_id=finding.get("rule_id", ""),
            function=finding.get("function"),
        )
        if not test_code:
            report.results.append(FixResult(
                **base, fix_verdict="inconclusive",
                reason="No reproducing test was recorded for this finding.",
            ))
            continue

        result = run_tests(
            source_code=repaired_source,
            test_code=test_code,
            source_filename=source_filename,
            source_origin=source_origin,
        )
        verdict, reason = _defect_gone(
            base["type"], result.passed, result.failed, result.errors,
        )
        report.results.append(FixResult(**base, fix_verdict=verdict, reason=reason))
    return report
