"""HumanEvalFix dataset loader.

Loads BigCode's HumanEvalFix (Python subset of ``bigcode/humanevalpack``).
Each record is a small program where a single bug has been introduced
into a HumanEval-canonical solution; the record carries both the buggy
and canonical bodies plus a unit-test suite.

This module exposes one public function: :func:`load_humanevalfix`. It
returns a list of :class:`HumanEvalProblem` dataclasses, in the dataset's
original order, optionally sliced and seeded for reproducibility.

Reproducibility
---------------

If ``sample_size`` is set, problems are sampled deterministically using
the supplied seed. The same seed always produces the same subset, in
the same order. The seed is recorded in the experiment manifest so a
reviewer can re-run the sampling.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional


# Dataset identifier on the Hugging Face Hub.
HUMANEVALFIX_DATASET = "bigcode/humanevalpack"
HUMANEVALFIX_CONFIG = "python"
HUMANEVALFIX_SPLIT = "test"


@dataclass(frozen=True)
class HumanEvalProblem:
    """One HumanEvalFix problem.

    Field semantics match the dataset's record schema; we keep the original
    names so a reader of the source can cross-reference.
    """

    task_id: str
    entry_point: str
    declaration: str
    prompt: str
    canonical_solution: str
    buggy_solution: str
    bug_type: str
    failure_symptoms: str
    test: str
    example_test: str = ""

    @property
    def canonical_full_source(self) -> str:
        """The full canonical program: declaration + canonical solution."""
        return self.declaration + self.canonical_solution

    @property
    def buggy_full_source(self) -> str:
        """The full buggy program: declaration + buggy solution."""
        return self.declaration + self.buggy_solution


def _record_to_problem(rec: dict) -> HumanEvalProblem:
    """Convert one dataset record into our typed problem object.

    Tolerant of missing fields with sensible defaults so a dataset version
    bump doesn't immediately break us.
    """
    return HumanEvalProblem(
        task_id=rec.get("task_id", ""),
        entry_point=rec.get("entry_point", ""),
        declaration=rec.get("declaration", ""),
        prompt=rec.get("prompt", ""),
        canonical_solution=rec.get("canonical_solution", ""),
        buggy_solution=rec.get("buggy_solution", ""),
        bug_type=rec.get("bug_type", ""),
        failure_symptoms=rec.get("failure_symptoms", ""),
        test=rec.get("test", ""),
        example_test=rec.get("example_test", ""),
    )


def load_humanevalfix(
    sample_size: Optional[int] = None,
    seed: int = 42,
    records: Optional[list[dict]] = None,
) -> list[HumanEvalProblem]:
    """Load HumanEvalFix problems.

    Args:
        sample_size: If set, return a deterministic random subset of this
            size. If None (default), return all 164 problems in dataset order.
        seed: Random seed used only when ``sample_size`` is set. Ignored
            otherwise. Recording this seed in the experiment manifest is
            essential for reproducibility.
        records: For tests, an in-memory list of dicts that mimics the
            dataset schema. When provided, skips the Hub call entirely.

    Returns:
        A list of HumanEvalProblem objects. Order is the dataset's original
        order if ``sample_size`` is None; otherwise sorted by ``task_id``
        so the subset is also deterministically ordered for reports.

    Raises:
        ImportError: if ``datasets`` is not installed.
        RuntimeError: if the Hub cannot be reached and no records are
            supplied. The error message tells the user to either install
            datasets or pass records explicitly.
    """
    if records is None:
        try:
            from datasets import load_dataset
        except ImportError as e:
            raise ImportError(
                "The 'datasets' package is required to load HumanEvalFix "
                "from the Hub. Install the experiments extras with:\n"
                "  pip install -e \".[experiments]\"\n"
                "or directly: pip install datasets"
            ) from e
        try:
            ds = load_dataset(
                HUMANEVALFIX_DATASET,
                HUMANEVALFIX_CONFIG,
                split=HUMANEVALFIX_SPLIT,
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to load {HUMANEVALFIX_DATASET}: {e}. "
                "Check your internet connection or pass records= explicitly."
            ) from e
        records = list(ds)

    problems = [_record_to_problem(r) for r in records]

    if sample_size is None:
        return problems

    if sample_size <= 0:
        raise ValueError(f"sample_size must be positive, got {sample_size}")
    if sample_size >= len(problems):
        # Asked for at-least-everything; return everything but in
        # task_id-sorted order for determinism alongside sampled runs.
        return sorted(problems, key=lambda p: p.task_id)

    rng = random.Random(seed)
    sampled = rng.sample(problems, sample_size)
    return sorted(sampled, key=lambda p: p.task_id)
