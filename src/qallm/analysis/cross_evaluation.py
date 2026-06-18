"""Cross-evaluation: run the final accumulated test suite against every code
variant produced in a session.

Motivation
----------
During a live session, round N's tests run only against round N's code variant
(see verification_manager.verify). Each variant is therefore judged with the
test suite as it stood at that moment, so ``test_pass_rate`` and ``bugs_caught``
are measured against *different* suites per round. That is an apples-to-oranges
comparison: a variant can look stronger merely because its round generated
gentler tests, not because the code is better.

Cross-evaluation removes that confound. After a session completes, it assembles
the *final* accumulated test suite per function (the strongest suite the session
ever produced) and runs it against *every* variant of that function, the
baseline and every accepted and abandoned variant. The result is a
variant x test-suite matrix in which every cell is measured against the same
yardstick, so variants can be compared on equal terms.

This is a post-hoc, read-only analysis. It does not touch the live judging
loop; it reads the persisted ``source.py`` and ``tests/`` artefacts that the
reporter already writes per round. It is the data foundation for the round
comparison table and for a sounder reliability comparison in the thesis.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from qallm.verification.executor import _parse_test_provenance, run_tests

# ----- helpers -----


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _content_hash(test_code: str) -> str:
    """Whitespace-normalised digest, matching test_persistence.StoredTest."""
    normalised = re.sub(r"\s+", " ", test_code).strip()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:8]


def _round_no(name: str) -> Optional[int]:
    try:
        return int(name.replace("round_", ""))
    except ValueError:
        return None


# ----- data model -----


@dataclass
class CellTest:
    """One test's outcome within a cell, for the per-test heat map."""

    name: str  # display name, provenance suffix stripped
    status: str  # passed | failed | error | skipped
    origin_round: Optional[int] = None  # round the test was generated in

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "origin_round": self.origin_round}


@dataclass
class VariantCell:
    """One cell of the matrix: a final suite run against one variant."""

    function_name: str
    round_number: int
    bucket: str  # "lineage" (accepted) or "abandoned" (rejected)
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    execution_error: Optional[str] = None
    tests: list[CellTest] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors + self.skipped

    @property
    def outcome(self) -> str:
        """A single colour-coded outcome for the comparison table.

        green: all tests passed; red: at least one failed (a real defect under
        the final suite); orange: an execution error prevented a clean verdict.
        """
        if self.execution_error or self.errors:
            return "error"
        if self.failed:
            return "fail"
        if self.passed:
            return "pass"
        return "none"

    def to_dict(self) -> dict:
        return {
            "function_name": self.function_name,
            "round_number": self.round_number,
            "bucket": self.bucket,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "total": self.total,
            "outcome": self.outcome,
            "execution_error": self.execution_error,
            "tests": [t.to_dict() for t in self.tests],
        }


@dataclass
class CrossEvaluation:
    """The full variant x final-suite matrix for one session."""

    functions: list[str] = field(default_factory=list)
    rounds: list[int] = field(default_factory=list)
    cells: list[VariantCell] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "functions": self.functions,
            "rounds": self.rounds,
            "cells": [c.to_dict() for c in self.cells],
        }


# ----- discovery -----


@dataclass
class _Variant:
    round_number: int
    bucket: str
    source: str
    unit_dir: str


def _discover_variants(report_dir: str) -> list[_Variant]:
    """Every persisted code variant, baseline plus accepted and abandoned."""
    variants: list[_Variant] = []
    for bucket in ("lineage", "abandoned"):
        bucket_dir = os.path.join(report_dir, bucket)
        if not os.path.isdir(bucket_dir):
            continue
        for round_name in sorted(os.listdir(bucket_dir)):
            rno = _round_no(round_name)
            if rno is None:
                continue
            round_path = os.path.join(bucket_dir, round_name)
            if not os.path.isdir(round_path):
                continue
            for unit_seg in sorted(os.listdir(round_path)):
                unit_dir = os.path.join(round_path, unit_seg)
                source = _read_text(os.path.join(unit_dir, "source.py"))
                if source:
                    variants.append(
                        _Variant(rno, bucket, source, unit_dir)
                    )
    return variants


def _collect_final_suites(variants: list[_Variant]) -> dict[str, str]:
    """Per function, the accumulated test suite across all rounds.

    Reads each variant's ``tests/test_<fn>.py`` files and unions them by
    content hash (so a test carried unchanged across rounds is counted once,
    while a same-named test with different logic is kept). Returns a mapping
    from function name to a single concatenated pytest module.
    """
    # function -> {hash: test_code}
    by_function: dict[str, dict[str, str]] = {}
    for v in variants:
        tests_dir = os.path.join(v.unit_dir, "tests")
        if not os.path.isdir(tests_dir):
            continue
        for fname in sorted(os.listdir(tests_dir)):
            if not fname.startswith("test_") or not fname.endswith(".py"):
                continue
            func = fname[len("test_"):-len(".py")]
            code = _read_text(os.path.join(tests_dir, fname))
            if not code.strip():
                continue
            by_function.setdefault(func, {})[_content_hash(code)] = code
    return {
        func: "\n\n".join(blocks.values())
        for func, blocks in by_function.items()
    }


def _function_in_source(source: str, function_name: str) -> bool:
    return re.search(rf"(?m)^\s*def\s+{re.escape(function_name)}\s*\(", source) is not None


def _expected_module_name(suite: str) -> Optional[str]:
    """The source module name the tests import from.

    Generated tests import the function under test with a line like
    ``from source_reliability_gap_c0 import inclusive_range_count``. The
    variant must be written to a file of that exact name or the import fails
    and pytest collects nothing. Recover the name from the first matching
    import so cross-evaluation does not depend on reconstructing the pipeline's
    naming scheme.
    """
    m = re.search(r"(?m)^\s*from\s+(source_\w+)\s+import\b", suite)
    return m.group(1) if m else None


# ----- the matrix -----


def cross_evaluate(report_dir: str) -> CrossEvaluation:
    """Run each function's final accumulated suite against every variant.

    Read-only. Safe to call on a completed session's report directory.
    """
    variants = _discover_variants(report_dir)
    final_suites = _collect_final_suites(variants)

    result = CrossEvaluation()
    result.rounds = sorted({v.round_number for v in variants})
    result.functions = sorted(final_suites.keys())

    for func, suite in final_suites.items():
        # The tests import the function from a specific source module name; the
        # variant must be written under that name or the import fails and no
        # tests run. Fall back to a generic name if no import is present.
        expected = _expected_module_name(suite)
        module_basename = expected or "variant_source"
        for v in variants:
            # Only evaluate the suite against variants whose source actually
            # defines this function; otherwise an import error would masquerade
            # as a defect.
            if not _function_in_source(v.source, func):
                continue
            exec_result = run_tests(
                v.source, suite, f"{module_basename}.py", Path(v.unit_dir)
            )
            cell_tests: list[CellTest] = []
            for d in getattr(exec_result, "test_details", []) or []:
                origin, _tid, display = _parse_test_provenance(d.name)
                cell_tests.append(
                    CellTest(
                        name=display,
                        status=d.status,
                        origin_round=origin,
                    )
                )
            result.cells.append(
                VariantCell(
                    function_name=func,
                    round_number=v.round_number,
                    bucket=v.bucket,
                    passed=getattr(exec_result, "passed", 0),
                    failed=getattr(exec_result, "failed", 0),
                    errors=getattr(exec_result, "errors", 0),
                    skipped=getattr(exec_result, "skipped", 0),
                    execution_error=exec_result.execution_error,
                    tests=cell_tests,
                )
            )
    return result


def cross_evaluate_to_json(report_dir: str, out_path: Optional[str] = None) -> dict:
    """Compute the matrix and optionally write it to ``out_path``."""
    matrix = cross_evaluate(report_dir).to_dict()
    if out_path:
        Path(out_path).write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    return matrix
