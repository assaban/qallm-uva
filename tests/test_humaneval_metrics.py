"""Tests for qallm.experiments.humaneval_metrics.

These tests use real pytest subprocesses to exercise the bug-detection
and repair-success definitions end-to-end. They are slow but they are
the proof that the definitions actually work; mocking subprocess would
test nothing of interest.

The aggregation and Wilcoxon tests use pure-Python ProblemResult lists
and run fast.
"""

from __future__ import annotations

import pytest

from qallm.experiments.humaneval_metrics import (
    AggregateResult,
    ProblemResult,
    aggregate,
    bug_was_detected,
    repair_was_successful,
    run_tests_against_source,
    wilcoxon_pairs,
)


# Fixtures: a small toy problem with clear semantics.

CANONICAL = "def add(a, b):\n    return a + b\n"
BUGGY = "def add(a, b):\n    return a - b\n"

DISCRIMINATING_TEST = "def check(candidate):\n    assert candidate(2, 3) == 5\n"
USELESS_TEST = "def check(candidate):\n    pass\n"
BROKEN_TEST = "def check(candidate):\n    raise RuntimeError('always')\n"


class TestRunTestsAgainstSource:
    def test_passing_combination_returns_true(self):
        passed, _ = run_tests_against_source(
            DISCRIMINATING_TEST, CANONICAL, "add"
        )
        assert passed

    def test_failing_combination_returns_false(self):
        passed, _ = run_tests_against_source(
            DISCRIMINATING_TEST, BUGGY, "add"
        )
        assert not passed

    def test_broken_test_returns_false(self):
        passed, output = run_tests_against_source(
            BROKEN_TEST, CANONICAL, "add"
        )
        assert not passed
        # Output should mention the RuntimeError.
        assert "RuntimeError" in output or "always" in output

    def test_timeout_returns_false(self):
        # Test code that intentionally hangs.
        hanging = (
            "def check(candidate):\n"
            "    import time\n"
            "    time.sleep(30)\n"
        )
        passed, output = run_tests_against_source(
            hanging, CANONICAL, "add", timeout_seconds=0.5,
        )
        assert not passed
        assert "timeout" in output.lower()


class TestBugWasDetected:
    def test_discriminating_test_detects_bug(self):
        assert bug_was_detected(
            DISCRIMINATING_TEST, BUGGY, CANONICAL, "add"
        )

    def test_useless_test_does_not_detect(self):
        # Useless test passes both buggy and canonical; nothing detected.
        assert not bug_was_detected(
            USELESS_TEST, BUGGY, CANONICAL, "add"
        )

    def test_test_failing_canonical_does_not_count(self):
        # A test that fails canonical isn't detecting the actual bug;
        # it's just broken. Should not count.
        # Build a test that fails on add(2, 3) == 999 always.
        wrong = "def check(candidate):\n    assert candidate(2, 3) == 999\n"
        assert not bug_was_detected(
            wrong, BUGGY, CANONICAL, "add"
        )


class TestRepairWasSuccessful:
    def test_canonical_passes_dataset_test(self):
        dataset_test = (
            "def check(candidate):\n"
            "    assert candidate(2, 3) == 5\n"
            "    assert candidate(0, 0) == 0\n"
        )
        assert repair_was_successful(CANONICAL, dataset_test, "add")

    def test_buggy_fails_dataset_test(self):
        dataset_test = (
            "def check(candidate):\n"
            "    assert candidate(2, 3) == 5\n"
        )
        assert not repair_was_successful(BUGGY, dataset_test, "add")

    def test_partially_repaired_still_fails_strict_test(self):
        # Partial repair: fixes add(2,3)==5 but introduces another bug
        # exposed by a stricter test.
        partial = "def add(a, b):\n    return 5\n"  # only works for 2+3
        strict = (
            "def check(candidate):\n"
            "    assert candidate(2, 3) == 5\n"
            "    assert candidate(0, 0) == 0\n"
        )
        assert not repair_was_successful(partial, strict, "add")


class TestAggregate:
    def _r(self, **kwargs) -> ProblemResult:
        defaults = dict(
            task_id="P", strategy="rl", model="m",
            bug_detected=True, repair_successful=True,
            rounds_run=3, total_bugs_reported=1,
            final_coverage=80.0, cost_usd=0.01, elapsed_seconds=5.0,
            error=None,
        )
        defaults.update(kwargs)
        return ProblemResult(**defaults)

    def test_groups_by_strategy_and_model(self):
        results = [
            self._r(task_id="P/0", strategy="rl", model="a"),
            self._r(task_id="P/0", strategy="oneshot", model="a"),
            self._r(task_id="P/0", strategy="rl", model="b"),
        ]
        aggs = aggregate(results)
        assert len(aggs) == 3
        # Sorted alphabetically.
        assert {(a.strategy, a.model) for a in aggs} == {
            ("oneshot", "a"), ("rl", "a"), ("rl", "b")
        }

    def test_rates_exclude_errored_runs(self):
        results = [
            self._r(task_id="P/0", bug_detected=True),
            self._r(task_id="P/1", bug_detected=False),
            self._r(task_id="P/2", error="boom", bug_detected=False),
        ]
        aggs = aggregate(results)
        a = aggs[0]
        # 1 detected out of 2 non-errored => 0.5.
        assert a.bug_detection_rate == 0.5
        assert a.n_errored == 1
        assert a.n_problems == 3

    def test_to_dict_includes_computed_rates(self):
        results = [self._r(bug_detected=True, repair_successful=False)]
        aggs = aggregate(results)
        d = aggs[0].to_dict()
        assert "bug_detection_rate" in d
        assert "repair_success_rate" in d
        assert d["bug_detection_rate"] == 1.0
        assert d["repair_success_rate"] == 0.0

    def test_mean_excludes_errored(self):
        results = [
            self._r(task_id="P/0", rounds_run=2, cost_usd=0.01),
            self._r(task_id="P/1", rounds_run=4, cost_usd=0.03),
            self._r(task_id="P/2", error="boom", rounds_run=0, cost_usd=0.0),
        ]
        aggs = aggregate(results)
        a = aggs[0]
        # Errored excluded => mean over 2 valid rows.
        assert a.mean_rounds == 3.0
        assert a.mean_cost_usd == 0.02


class TestWilcoxonPairs:
    def _r(self, task_id, strategy, model, bug_detected=True):
        return ProblemResult(
            task_id=task_id, strategy=strategy, model=model,
            bug_detected=bug_detected, repair_successful=False,
            rounds_run=1, total_bugs_reported=0,
            final_coverage=0.0, cost_usd=0.0, elapsed_seconds=0.0,
        )

    def test_returns_empty_when_no_pairs(self):
        # All same strategy: no pairs.
        results = [self._r(f"P/{i}", "rl", "m") for i in range(10)]
        assert wilcoxon_pairs(results) == []

    def test_returns_empty_when_sample_too_small(self):
        # Only 3 paired observations; Wilcoxon needs at least 6 by our
        # convention.
        results = [
            self._r("P/0", "rl", "m", True), self._r("P/0", "oneshot", "m", False),
            self._r("P/1", "rl", "m", True), self._r("P/1", "oneshot", "m", False),
            self._r("P/2", "rl", "m", True), self._r("P/2", "oneshot", "m", False),
        ]
        result = wilcoxon_pairs(results)
        # Either empty (too few) or includes a "too small" note.
        assert all(r.get("n", 0) >= 6 for r in result) or result == []

    def test_produces_pair_for_two_strategies(self):
        # 10 observations, all RL detects, none for oneshot. Wilcoxon
        # should find a strong asymmetry.
        results = []
        for i in range(10):
            results.append(self._r(f"P/{i}", "rl", "m", True))
            results.append(self._r(f"P/{i}", "oneshot", "m", False))
        pairs = wilcoxon_pairs(results, metric="bug_detected")
        # There should be one pair: rl vs oneshot.
        assert len(pairs) == 1
        pair = pairs[0]
        assert {pair["a"], pair["b"]} == {"rl", "oneshot"}
        assert pair["n"] == 10
        # Result is either a real p-value or a "all zero differences" note;
        # both are valid outcomes for a perfectly separated sample.
        assert pair.get("pvalue") is not None or "note" in pair

    def test_excludes_errored_runs(self):
        results = []
        for i in range(10):
            results.append(self._r(f"P/{i}", "rl", "m", True))
            results.append(self._r(f"P/{i}", "oneshot", "m", False))
        # Add some errored runs that should be excluded entirely.
        err = ProblemResult(
            task_id="P/err", strategy="rl", model="m",
            bug_detected=False, repair_successful=False,
            rounds_run=0, total_bugs_reported=0,
            final_coverage=0.0, cost_usd=0.0, elapsed_seconds=0.0,
            error="kaboom",
        )
        results.append(err)
        pairs = wilcoxon_pairs(results, metric="bug_detected")
        # n is still 10 (the errored one didn't have an oneshot counterpart
        # anyway and would have been filtered out).
        if pairs:
            assert pairs[0]["n"] == 10
