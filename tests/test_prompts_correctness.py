"""Tests for the correctness oracle prompt (reliability-bug detection)."""

from qallm.verification.extractor import FunctionInfo
from qallm.verification.prompts import build_correctness_oracle_prompt
from qallm.verification.generator import PROMPT_BUILDERS


def _fi():
    return FunctionInfo(
        name="inclusive_range_count",
        source="def inclusive_range_count(start, end):\n    return end - start",
        docstring="Count integers from start to end inclusive.",
        args=[("start", None), ("end", None)],
        lineno=1, filepath="x.py",
    )


def test_correctness_oracle_registered():
    assert "correctness" in PROMPT_BUILDERS


def test_correctness_prompt_treats_docstring_as_truth():
    p = build_correctness_oracle_prompt(_fi())
    assert "SOURCE OF TRUTH" in p
    assert "MAY BE WRONG" in p  # implementation may be buggy


def test_correctness_prompt_demands_value_assertions():
    p = build_correctness_oracle_prompt(_fi())
    assert "exact value" in p.lower()
    assert "isinstance" in p  # explicitly discouraged
