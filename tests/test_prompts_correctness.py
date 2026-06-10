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
    assert "body is withheld" in p  # implementation not shown, so no anchoring


def test_correctness_prompt_demands_value_assertions():
    p = build_correctness_oracle_prompt(_fi())
    assert "exact value" in p.lower()
    assert "isinstance" in p  # explicitly discouraged


def test_correctness_prompt_withholds_implementation_body():
    # The body must NOT appear (it anchors the model on buggy behaviour); the
    # signature must.
    fi = FunctionInfo(
        name="inclusive_range_count",
        source="def inclusive_range_count(start, end):\n    return end - start",
        docstring="Count integers from start to end inclusive.",
        args=[("start", None), ("end", None)], lineno=1, filepath="x.py",
    )
    p = build_correctness_oracle_prompt(fi)
    assert "return end - start" not in p          # body withheld
    assert "def inclusive_range_count(start, end)" in p  # signature shown


def test_correctness_prompt_has_stateful_and_return_guidance():
    fi = FunctionInfo(
        name="f", source="def f(x):\n    return x", docstring="d",
        args=[("x", None)], lineno=1, filepath="x.py",
    )
    p = build_correctness_oracle_prompt(fi)
    assert "MULTIPLE calls" in p          # cross-call defects (accumulate class)
    assert "do not assert it raises" in p  # return-not-raise (safe_divide class)


def test_signature_only_falls_back_when_unparseable():
    from qallm.verification.prompts import _signature_only
    fi = FunctionInfo(name="g", source="", docstring="", args=[("a", None)],
                      lineno=1, filepath="x.py")
    assert _signature_only(fi) == "def g(a):"
