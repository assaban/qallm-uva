"""Tests for qallm.experiments.humaneval_dataset.

Covers loading from in-memory records, sampling determinism, and
graceful error handling. Hub access is not tested (network-bound; the
function delegates straightforwardly to ``datasets.load_dataset``).
"""

from __future__ import annotations

import pytest

from qallm.experiments.humaneval_dataset import (
    HumanEvalProblem,
    load_humanevalfix,
)


def _sample_records(n: int = 5) -> list[dict]:
    return [
        {
            "task_id": f"Python/{i}",
            "entry_point": f"fn_{i}",
            "declaration": f"def fn_{i}(x):\n",
            "canonical_solution": "    return x\n",
            "buggy_solution": "    return None\n",
            "bug_type": "value misuse",
            "failure_symptoms": "returns None instead of x",
            "test": "def check(candidate):\n    assert candidate(1) == 1\n",
            "example_test": "",
        }
        for i in range(n)
    ]


class TestLoadAllRecords:
    def test_returns_one_problem_per_record(self):
        problems = load_humanevalfix(records=_sample_records(3))
        assert len(problems) == 3
        assert all(isinstance(p, HumanEvalProblem) for p in problems)

    def test_preserves_original_order_when_unsampled(self):
        problems = load_humanevalfix(records=_sample_records(5))
        assert [p.task_id for p in problems] == [
            "Python/0", "Python/1", "Python/2", "Python/3", "Python/4",
        ]

    def test_full_source_assembles_correctly(self):
        problems = load_humanevalfix(records=_sample_records(1))
        p = problems[0]
        assert p.buggy_full_source == "def fn_0(x):\n    return None\n"
        assert p.canonical_full_source == "def fn_0(x):\n    return x\n"


class TestSampling:
    def test_sample_size_returns_correct_count(self):
        problems = load_humanevalfix(
            records=_sample_records(20), sample_size=5, seed=42,
        )
        assert len(problems) == 5

    def test_sampling_is_deterministic_for_same_seed(self):
        recs = _sample_records(20)
        a = load_humanevalfix(records=recs, sample_size=5, seed=42)
        b = load_humanevalfix(records=recs, sample_size=5, seed=42)
        assert [p.task_id for p in a] == [p.task_id for p in b]

    def test_different_seeds_give_different_samples(self):
        recs = _sample_records(20)
        a = load_humanevalfix(records=recs, sample_size=5, seed=1)
        b = load_humanevalfix(records=recs, sample_size=5, seed=2)
        # With 20 records and a 5-element sample, two different seeds
        # producing identical samples is astronomically unlikely.
        assert [p.task_id for p in a] != [p.task_id for p in b]

    def test_sample_size_at_or_above_total_returns_all_sorted(self):
        recs = _sample_records(5)
        problems = load_humanevalfix(records=recs, sample_size=5, seed=1)
        # All five returned, sorted by task_id.
        assert len(problems) == 5
        assert [p.task_id for p in problems] == [
            "Python/0", "Python/1", "Python/2", "Python/3", "Python/4",
        ]

    def test_sample_size_above_total_does_not_raise(self):
        problems = load_humanevalfix(
            records=_sample_records(5), sample_size=100, seed=1,
        )
        assert len(problems) == 5

    def test_sampled_results_sorted_by_task_id(self):
        problems = load_humanevalfix(
            records=_sample_records(20), sample_size=10, seed=99,
        )
        task_ids = [p.task_id for p in problems]
        assert task_ids == sorted(task_ids)


class TestValidation:
    def test_zero_sample_size_raises(self):
        with pytest.raises(ValueError):
            load_humanevalfix(records=_sample_records(5), sample_size=0)

    def test_negative_sample_size_raises(self):
        with pytest.raises(ValueError):
            load_humanevalfix(records=_sample_records(5), sample_size=-3)


class TestMissingFieldsTolerance:
    """A dataset version bump should not catastrophically break us."""

    def test_missing_optional_fields_use_empty_defaults(self):
        recs = [{
            "task_id": "Python/0", "entry_point": "f",
            "declaration": "def f(): pass\n",
            "canonical_solution": "", "buggy_solution": "",
            "test": "",
        }]
        problems = load_humanevalfix(records=recs)
        assert problems[0].bug_type == ""
        assert problems[0].failure_symptoms == ""
        assert problems[0].example_test == ""
