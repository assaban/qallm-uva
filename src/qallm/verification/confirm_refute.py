"""Confirm or refute individual static findings by execution.

Roadmap step 3. The gap view (step 2) correlates findings to functions:
useful, but only at function granularity. This module sharpens the claim to
the level of a single finding: take one static finding, generate a test
whose explicit job is to demonstrate that finding's defect, run it, and
record whether the finding reproduced.

Crucially this is *type-aware*, because not every static finding is
something execution can speak to:

* RELIABILITY (a correctness bug): a test can reproduce it by making the
  function return a wrong result or raise. Confirmable.
* SECURITY (a vulnerability such as eval / shell=True): a test can
  demonstrate the unsafe behaviour is reachable. Confirmable as
  exploitability.
* COMPLEXITY / MAINTAINABILITY: a property of the source text (e.g. high
  cyclomatic complexity), not a runtime behaviour. No test can "reproduce"
  it, so we never attempt one and label it not_execution_testable. Pretending
  otherwise would be dishonest and waste an LLM call.

A finding's verdict is therefore one of:
  - confirmed: the targeted test demonstrated the defect.
  - refuted: the targeted test ran cleanly, the finding was not reproducible
    by the generated test (a candidate false positive, stated cautiously).
  - inconclusive: the test could not be generated or errored (no evidence).
  - not_execution_testable: the finding type is not something execution can
    judge.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from qallm.verification.executor import run_tests
from qallm.verification.generator import _fix_source_import, _validate_test_code
from qallm.verification.models import FunctionInfo
from qallm.verification.prompts import (
    SYSTEM_PROMPT,
    build_finding_targeted_prompt,
)
from qallm.verification.sandbox import CodeExtractor
from qallm.verification.test_validator import strip_unsatisfied_fixture_tests

logger = logging.getLogger(__name__)

Verdict = Literal[
    "confirmed", "refuted", "inconclusive", "not_execution_testable",
]

# Finding types execution can speak to, and how the targeted test's outcome
# maps to a verdict.
#   RELIABILITY: the test asserts CORRECT behaviour, so a FAILURE means the
#     bug reproduced (confirmed); a pass means not reproduced (refuted).
#   SECURITY: the test asserts the unsafe effect OCCURS, so a PASS means the
#     vulnerability is demonstrated (confirmed); a failure means it did not
#     trigger (refuted).
_RELIABILITY_TYPES = {"RELIABILITY"}
_SECURITY_TYPES = {"SECURITY"}
_TESTABLE_TYPES = _RELIABILITY_TYPES | _SECURITY_TYPES


@dataclass
class FindingVerdict:
    finding_index: int
    tool: str
    type: str
    severity: str
    line: int
    message: str
    rule_id: str
    function: str | None
    verdict: Verdict
    reason: str
    reproducing_test: str | None = None  # the test body, when confirmed

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_index": self.finding_index,
            "tool": self.tool, "type": self.type, "severity": self.severity,
            "line": self.line, "message": self.message,
            "rule_id": self.rule_id, "function": self.function,
            "verdict": self.verdict, "reason": self.reason,
            "reproducing_test": self.reproducing_test,
        }


@dataclass
class ConfirmRefuteReport:
    verdicts: list[FindingVerdict] = field(default_factory=list)

    @property
    def confirmed(self) -> int:
        return sum(1 for v in self.verdicts if v.verdict == "confirmed")

    @property
    def refuted(self) -> int:
        return sum(1 for v in self.verdicts if v.verdict == "refuted")

    @property
    def inconclusive(self) -> int:
        return sum(1 for v in self.verdicts if v.verdict == "inconclusive")

    @property
    def not_testable(self) -> int:
        return sum(1 for v in self.verdicts
                   if v.verdict == "not_execution_testable")

    @property
    def confirmation_rate(self) -> float | None:
        """Confirmed over the findings we actually tested (confirmed +
        refuted). None when nothing was testable/attempted."""
        denom = self.confirmed + self.refuted
        return (self.confirmed / denom) if denom else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdicts": [v.to_dict() for v in self.verdicts],
            "summary": {
                "confirmed": self.confirmed,
                "refuted": self.refuted,
                "inconclusive": self.inconclusive,
                "not_execution_testable": self.not_testable,
                "confirmation_rate": self.confirmation_rate,
            },
        }


def _classify_outcome(ftype: str, passed: int, failed: int, errors: int) -> tuple[Verdict, str]:
    """Map a targeted test's run outcome to a verdict, by finding type."""
    if errors > 0 and passed == 0 and failed == 0:
        return "inconclusive", "The targeted test errored before running."
    if ftype in _RELIABILITY_TYPES:
        if failed > 0:
            return "confirmed", (
                "A targeted test asserting correct behaviour failed against "
                "the current code, reproducing the defect."
            )
        if passed > 0:
            return "refuted", (
                "Targeted tests asserting correct behaviour passed; the "
                "finding was not reproducible by the generated test."
            )
        return "inconclusive", "No targeted test produced a clear result."
    # SECURITY: a passing test demonstrates the unsafe effect occurs.
    if passed > 0:
        return "confirmed", (
            "A targeted test demonstrated the flagged unsafe behaviour is "
            "reachable."
        )
    if failed > 0:
        return "refuted", (
            "The targeted test could not demonstrate the unsafe behaviour; "
            "the finding was not reproduced."
        )
    return "inconclusive", "No targeted test produced a clear result."


class FindingConfirmer:
    """Generates and runs a targeted test per finding to reach a verdict."""

    def __init__(self, llm, tracker=None) -> None:
        self.llm = llm
        self.tracker = tracker

    def confirm_findings(
        self,
        func: FunctionInfo,
        findings: list[dict],
        source_code: str,
        source_filename: str = "source_module.py",
        source_origin=None,
    ) -> ConfirmRefuteReport:
        """Reach a verdict for each finding that maps to ``func``.

        Findings whose type execution cannot judge are recorded as
        not_execution_testable without an LLM call. The rest get a targeted
        test, executed in the sandbox.
        """
        report = ConfirmRefuteReport()
        module_name = source_filename.removesuffix(".py")
        for idx, finding in enumerate(findings):
            ftype = (finding.get("type") or "").upper()
            base = dict(
                finding_index=idx,
                tool=finding.get("tool", "?"),
                type=ftype or "?",
                severity=finding.get("severity", "?"),
                line=int(finding.get("line", 0) or 0),
                message=finding.get("message", ""),
                rule_id=finding.get("rule_id", ""),
                function=func.name,
            )
            if ftype not in _TESTABLE_TYPES:
                report.verdicts.append(FindingVerdict(
                    **base,
                    verdict="not_execution_testable",
                    reason=(
                        f"A {ftype or 'non-runtime'} finding is a property of "
                        "the source, not a runtime behaviour; execution "
                        "cannot confirm or refute it."
                    ),
                ))
                continue

            verdict, reason, test_body = self._attempt(
                func, finding, module_name, source_code,
                source_filename, source_origin,
            )
            report.verdicts.append(FindingVerdict(
                **base, verdict=verdict, reason=reason,
                reproducing_test=test_body if verdict == "confirmed" else None,
            ))
        return report

    def _attempt(
        self, func, finding, module_name, source_code,
        source_filename, source_origin,
    ) -> tuple[Verdict, str, str | None]:
        ftype = (finding.get("type") or "").upper()
        prompt = build_finding_targeted_prompt(func, finding)
        resp = self.llm.chat(SYSTEM_PROMPT, prompt, self.tracker)
        if resp.error:
            return "inconclusive", f"Test generation failed: {resp.error}", None

        code, _ = CodeExtractor.extract(resp.content)
        code = _fix_source_import(code, module_name)
        is_valid, err = _validate_test_code(code)
        if is_valid:
            code, _discarded = strip_unsatisfied_fixture_tests(code)
            is_valid, err = _validate_test_code(code)
        if not is_valid:
            return "inconclusive", f"Generated test was invalid: {err}", None

        result = run_tests(
            source_code=source_code,
            test_code=code,
            source_filename=source_filename,
            source_origin=source_origin,
        )
        verdict, reason = _classify_outcome(
            ftype, result.passed, result.failed, result.errors,
        )
        return verdict, reason, code
