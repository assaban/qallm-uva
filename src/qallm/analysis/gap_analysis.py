"""Correlate static-analysis findings with execution results: the gap.

The thesis claim is that execution catches defects static analysis misses
(the "verification gap"), and that some static findings are not reproducible
by execution (candidate false positives). This module computes that
correlation per round from the persisted artefacts, so it can be shown for
any session, live or historical.

For each round we have, on disk:
- ``source.py``: the code as analysed that round.
- ``static.json``: the static findings (tool, line, severity, message).
- ``verification.json``: per-function execution results, including the
  generated tests and which of them failed (a failure is an
  execution-found bug; an error is a test that never ran and is not
  evidence either way).

Correlation is line-level: each finding's line is mapped to the function
whose line span contains it (computed by AST). A finding is then classified
against that function's execution outcome:

- ``confirmed``: the function has at least one execution-found bug, so
  execution corroborates that something is wrong where the finding points.
- ``unconfirmed``: the function was tested (tests ran) but produced no
  execution-found bug, so the finding is not reproduced. A candidate false
  positive, or simply not triggerable by the generated tests.
- ``untested``: the function had no tests that actually ran (all errored,
  or none generated), so there is no execution evidence either way.

The gap itself runs the other direction: an execution-found bug in a
function that has *no* static finding on it is a defect static analysis
missed. Those are counted as ``execution_only`` bugs, the heart of the
claim.

Counts deliberately exclude discarded and errored tests: only tests that
ran and failed are bugs, so the gap number is not polluted by tests that
never executed (the ERROR-vs-BUG distinction established earlier).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Literal

FindingStatus = Literal["confirmed", "unconfirmed", "untested"]


@dataclass
class FunctionSpan:
    name: str
    start: int
    end: int

    def contains(self, line: int) -> bool:
        return self.start <= line <= self.end


@dataclass
class ClassifiedFinding:
    tool: str
    severity: str
    line: int
    message: str
    rule_id: str
    function: str | None  # the function the line falls in, if any
    status: FindingStatus


@dataclass
class FunctionExecution:
    name: str
    ran: int  # tests that actually ran (passed + failed)
    bugs: int  # tests that ran and failed
    errors: int  # tests that errored (never ran)

    @property
    def tested(self) -> bool:
        return self.ran > 0

    @property
    def has_bug(self) -> bool:
        return self.bugs > 0


@dataclass
class GapReport:
    round: int
    findings: list[ClassifiedFinding] = field(default_factory=list)
    # Functions with an execution-found bug but no static finding: the gap.
    execution_only_functions: list[str] = field(default_factory=list)

    @property
    def confirmed(self) -> int:
        return sum(1 for f in self.findings if f.status == "confirmed")

    @property
    def unconfirmed(self) -> int:
        return sum(1 for f in self.findings if f.status == "unconfirmed")

    @property
    def untested(self) -> int:
        return sum(1 for f in self.findings if f.status == "untested")

    @property
    def confirmation_rate(self) -> float | None:
        """Confirmed over (confirmed + unconfirmed): of findings we could
        test, the fraction execution corroborated. None when nothing was
        testable."""
        denom = self.confirmed + self.unconfirmed
        return (self.confirmed / denom) if denom else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "findings": [
                {
                    "tool": f.tool, "severity": f.severity, "line": f.line,
                    "message": f.message, "rule_id": f.rule_id,
                    "function": f.function, "status": f.status,
                }
                for f in self.findings
            ],
            "execution_only_functions": self.execution_only_functions,
            "summary": {
                "confirmed": self.confirmed,
                "unconfirmed": self.unconfirmed,
                "untested": self.untested,
                "execution_only": len(self.execution_only_functions),
                "confirmation_rate": self.confirmation_rate,
            },
        }


def function_spans(source: str) -> list[FunctionSpan]:
    """Line spans of top-level and nested functions in the source.

    Uses end_lineno (Python 3.8+). A finding on a line inside a function
    body maps to that function; the most specific (innermost, smallest)
    enclosing function wins when functions nest.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    spans: list[FunctionSpan] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", None) or node.lineno
            spans.append(FunctionSpan(node.name, node.lineno, end))
    return spans


def _function_for_line(spans: list[FunctionSpan], line: int) -> str | None:
    """The innermost function whose span contains the line, or None."""
    best: FunctionSpan | None = None
    for s in spans:
        if s.contains(line):
            if best is None or (s.end - s.start) < (best.end - best.start):
                best = s
    return best.name if best else None


def _executions_from_verification(verification: list | None) -> dict[str, FunctionExecution]:
    """Map function name -> execution outcome from a round's verification.json.

    Reads the last round of each function's session (the final state that
    round), counting tests that ran (passed/failed) vs errored, mirroring
    the bug-detail summary used elsewhere.
    """
    out: dict[str, FunctionExecution] = {}
    if not verification:
        return out
    for session in verification:
        rounds = session.get("rounds") or []
        if not rounds:
            continue
        execution = (rounds[-1].get("execution") or {})
        name = session.get("function") or session.get("function_name") or "?"
        passed = int(execution.get("passed", 0) or 0)
        failed = int(execution.get("failed", 0) or 0)
        errors = int(execution.get("errors", 0) or 0)
        out[name] = FunctionExecution(
            name=name, ran=passed + failed, bugs=failed, errors=errors,
        )
    return out


def build_gap_report(
    round_no: int,
    source: str,
    findings: list[dict],
    verification: list | None,
) -> GapReport:
    """Classify each static finding against execution, and find the gap.

    ``findings`` is a list of finding dicts (tool, line, severity, message,
    rule_id) as persisted in static.json. ``verification`` is the parsed
    verification.json for the same round.
    """
    spans = function_spans(source)
    execs = _executions_from_verification(verification)
    report = GapReport(round=round_no)

    functions_with_finding: set[str] = set()
    for f in findings:
        line = int(f.get("line", 0) or 0)
        fn = _function_for_line(spans, line)
        if fn:
            functions_with_finding.add(fn)
        status: FindingStatus
        ex = execs.get(fn) if fn else None
        if ex is None or not ex.tested:
            status = "untested"
        elif ex.has_bug:
            status = "confirmed"
        else:
            status = "unconfirmed"
        report.findings.append(ClassifiedFinding(
            tool=f.get("tool", "?"),
            severity=f.get("severity", "?"),
            line=line,
            message=f.get("message", ""),
            rule_id=f.get("rule_id", ""),
            function=fn,
            status=status,
        ))

    # The gap: functions with an execution-found bug but no static finding.
    for name, ex in execs.items():
        if ex.has_bug and name not in functions_with_finding:
            report.execution_only_functions.append(name)
    report.execution_only_functions.sort()

    return report
