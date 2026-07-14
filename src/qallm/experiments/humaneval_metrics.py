"""Metrics for the HumanEvalFix experiment.

This module computes the two primary definitions of success and aggregates
them across problems. It deliberately separates the *measurement* logic
from the *running* logic so each can be tested independently.

Definitions
-----------

**Bug detected.** QALLM's generated tests, run against the buggy solution,
fail; AND those same tests, run against the canonical solution, pass.
The second clause is the safeguard: tests that fail everything are not
"detecting" anything; we want tests that distinguish buggy from canonical.

**Repair successful.** QALLM's repaired code passes the dataset's hidden
test suite (the ``test`` field of the HumanEvalFix record). This grounds
"fixed" in the external oracle rather than QALLM's own tests, which would
be circular.

These definitions match the bug-detection literature's standard "true
positive on test inputs" pattern. They are intentionally strict: we
prefer false negatives over false positives in the headline numbers.
"""

from __future__ import annotations

import subprocess
import sys
import re
import tempfile
import textwrap
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class ProblemResult:
    """The outcome of running QALLM on one HumanEvalFix problem."""

    task_id: str
    strategy: str
    model: str
    bug_detected: bool
    repair_successful: bool
    rounds_run: int
    total_bugs_reported: int
    final_coverage: float
    cost_usd: float
    elapsed_seconds: float
    error: Optional[str] = None  # populated when the run failed mid-way

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AggregateResult:
    """Headline numbers for one (strategy, model) combination."""

    strategy: str
    model: str
    n_problems: int
    n_bug_detected: int
    n_repair_successful: int
    n_errored: int
    mean_rounds: float
    mean_cost_usd: float
    mean_elapsed_seconds: float

    @property
    def bug_detection_rate(self) -> float:
        # Errors are excluded from rates to avoid penalising a strategy
        # for infrastructure failures unrelated to its quality.
        n = self.n_problems - self.n_errored
        return self.n_bug_detected / n if n else 0.0

    @property
    def repair_success_rate(self) -> float:
        n = self.n_problems - self.n_errored
        return self.n_repair_successful / n if n else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["bug_detection_rate"] = self.bug_detection_rate
        d["repair_success_rate"] = self.repair_success_rate
        return d


# ---------- bug-detection check ----------


def run_tests_against_source(
    test_code: str,
    target_source: str,
    entry_point: str,
    timeout_seconds: float = 10.0,
) -> tuple[bool, str]:
    """Run a unit-test suite against a target source string.

    Writes both to a temp directory, runs pytest as a subprocess, and
    returns ``(passed, captured_output)``. ``passed`` is True iff pytest
    exits cleanly (return code 0).

    The test code expects the target's ``entry_point`` function to be
    importable. We name the target file after the entry point and adjust
    the test's imports so they resolve.

    Args:
        test_code: Python source of the test suite. Must define a
            ``check(candidate)`` function per HumanEvalFix convention,
            or test functions that import the target by ``entry_point``.
        target_source: Python source of the function under test.
        entry_point: Name of the function the tests will call.
        timeout_seconds: Subprocess timeout to prevent hangs on bad code.

    Returns:
        Tuple of (passed, output). On timeout, passed is False and
        output describes the timeout.
    """
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Write the target as a top-level module.
        (td_path / f"{entry_point}_module.py").write_text(target_source)

        # QALLM's harvested tests carry their OWN import line, typically
        # `from source_<unit>_c0 import <fn>`, pointing at a module name that
        # does not exist here. If the target is not also written under that
        # name, every QALLM test errors at import, pytest exits non-zero on
        # buggy AND canonical alike, and detection is False for every problem
        # (the uniform-zero observed in the 2026-07-09 run). Satisfy the
        # test's own imports by writing the same target under each module
        # name the test imports from.
        for mod in set(re.findall(r"(?m)^\s*from\s+(source_\w+)\s+import\b",
                                  test_code)):
            (td_path / f"{mod}.py").write_text(target_source)

        # HumanEvalFix tests typically end with `check(<entry_point>)`.
        # We prepend an import that brings the entry_point into scope.
        # The `check` function name is the dataset convention.
        runner = textwrap.dedent(f"""
            from {entry_point}_module import {entry_point}
        """).strip() + "\n" + test_code
        # Only wrap the dataset convention. HumanEvalFix tests define
        # check(candidate); QALLM's harvested tests define plain pytest
        # functions and no check(), so appending the wrapper unconditionally
        # raised NameError and forced every QALLM detection run to fail
        # regardless of the code under test.
        if re.search(r"(?m)^\s*def\s+check\s*\(", test_code):
            runner += textwrap.dedent(f"""

                def test_humanevalfix_canonical():
                    check({entry_point})
            """)
        (td_path / "test_runner.py").write_text(runner)

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--no-header",
                 "test_runner.py"],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            return (result.returncode == 0, result.stdout + result.stderr)
        except subprocess.TimeoutExpired:
            return (False, f"timeout after {timeout_seconds}s")
        except Exception as e:
            return (False, f"runner error: {e}")


def bug_was_detected(
    qallm_test_code: str,
    buggy_source: str,
    canonical_source: str,
    entry_point: str,
) -> bool:
    """Apply the "bug detected" definition.

    A bug is *detected* iff QALLM's tests fail against the buggy code AND
    pass against the canonical code. The second clause excludes test
    suites that just fail everything.
    """
    passed_buggy, _ = run_tests_against_source(
        qallm_test_code, buggy_source, entry_point
    )
    if passed_buggy:
        # QALLM's tests passed against buggy code: they did not detect anything.
        return False
    # QALLM's tests failed against buggy code. Now check the discriminating
    # clause: do those same tests pass against canonical code?
    passes_canonical, _ = run_tests_against_source(
        qallm_test_code, canonical_source, entry_point
    )
    return passes_canonical


def repair_was_successful(
    repaired_source: str,
    dataset_test: str,
    entry_point: str,
) -> bool:
    """Apply the "repair successful" definition.

    Repair succeeds iff the dataset's hidden test suite passes against the
    repaired source. This grounds "fixed" in an external oracle.
    """
    passed, _ = run_tests_against_source(
        dataset_test, repaired_source, entry_point
    )
    return passed


# ---------- aggregation ----------


def aggregate(results: list[ProblemResult]) -> list[AggregateResult]:
    """Group per-problem results into per-(strategy, model) aggregates."""
    groups: dict[tuple[str, str], list[ProblemResult]] = {}
    for r in results:
        groups.setdefault((r.strategy, r.model), []).append(r)

    aggs = []
    for (strategy, model), items in sorted(groups.items()):
        n = len(items)
        n_errored = sum(1 for r in items if r.error is not None)
        n_detected = sum(1 for r in items if r.bug_detected and r.error is None)
        n_repaired = sum(1 for r in items if r.repair_successful and r.error is None)

        valid = [r for r in items if r.error is None]
        mean_rounds = sum(r.rounds_run for r in valid) / len(valid) if valid else 0.0
        mean_cost = sum(r.cost_usd for r in valid) / len(valid) if valid else 0.0
        mean_time = sum(r.elapsed_seconds for r in valid) / len(valid) if valid else 0.0

        aggs.append(AggregateResult(
            strategy=strategy,
            model=model,
            n_problems=n,
            n_bug_detected=n_detected,
            n_repair_successful=n_repaired,
            n_errored=n_errored,
            mean_rounds=mean_rounds,
            mean_cost_usd=mean_cost,
            mean_elapsed_seconds=mean_time,
        ))
    return aggs


def wilcoxon_pairs(
    results: list[ProblemResult],
    metric: str = "bug_detected",
) -> list[dict]:
    """Compute pairwise Wilcoxon signed-rank tests between strategies.

    For each pair of strategies sharing a (task_id, model), build the
    paired sample and test it. ``metric`` selects which 0/1 outcome to
    test: ``bug_detected`` or ``repair_successful``.

    Returns a list of dicts: ``{a, b, model, n, statistic, pvalue}``.
    Empty list if scipy is not available.
    """
    try:
        from scipy.stats import wilcoxon
    except ImportError:
        return []

    # Index: (strategy, model, task_id) -> bool
    by_key: dict[tuple[str, str, str], bool] = {}
    strategies: set[str] = set()
    models: set[str] = set()
    for r in results:
        if r.error is not None:
            continue
        value = bool(getattr(r, metric))
        by_key[(r.strategy, r.model, r.task_id)] = value
        strategies.add(r.strategy)
        models.add(r.model)

    out = []
    sorted_strats = sorted(strategies)
    for model in sorted(models):
        for i, a in enumerate(sorted_strats):
            for b in sorted_strats[i + 1:]:
                # Build paired samples on shared task_ids.
                a_vals: list[int] = []
                b_vals: list[int] = []
                # All task_ids present for both.
                tasks = sorted(
                    {k[2] for k in by_key if k[0] == a and k[1] == model}
                    & {k[2] for k in by_key if k[0] == b and k[1] == model}
                )
                if len(tasks) < 6:
                    # Wilcoxon needs a non-trivial sample.
                    continue
                for t in tasks:
                    a_vals.append(int(by_key[(a, model, t)]))
                    b_vals.append(int(by_key[(b, model, t)]))
                if all(av == bv for av, bv in zip(a_vals, b_vals)):
                    # All differences zero; wilcoxon would fail. Report n/a.
                    out.append({
                        "a": a, "b": b, "model": model, "metric": metric,
                        "n": len(tasks),
                        "statistic": None, "pvalue": None,
                        "note": "all differences zero",
                    })
                    continue
                try:
                    stat, p = wilcoxon(a_vals, b_vals, zero_method="wilcox")
                    out.append({
                        "a": a, "b": b, "model": model, "metric": metric,
                        "n": len(tasks),
                        "statistic": float(stat),
                        "pvalue": float(p),
                    })
                except Exception as e:
                    out.append({
                        "a": a, "b": b, "model": model, "metric": metric,
                        "n": len(tasks),
                        "statistic": None, "pvalue": None,
                        "note": str(e),
                    })
    return out
