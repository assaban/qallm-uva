"""Tests for mutation-based oracle confidence scoring."""

from qallm.verification.mutation_score import (
    MutationScore,
    _module_name_from_tests,
    score_oracle,
)


SRC = "def inc(start, end):\n    return end - start + 1\n"


def test_strong_oracle_scores_high():
    strong = (
        "from source_module import inc\n"
        "def test_a():\n    assert inc(0, 10) == 11\n"
        "def test_b():\n    assert inc(5, 5) == 1\n"
        "def test_c():\n    assert inc(1, 4) == 4\n"
    )
    s = score_oracle(SRC, "inc", strong)
    assert s.confidence == "high"
    assert s.score == 1.0
    assert s.killed == s.viable


def test_weak_oracle_scores_low():
    weak = (
        "from source_module import inc\n"
        "def test_a():\n    assert isinstance(inc(0, 10), int)\n"
        "def test_b():\n    assert isinstance(inc(1, 4), int)\n"
    )
    s = score_oracle(SRC, "inc", weak)
    # type-only checks miss value mutants
    assert s.confidence in ("low", "medium")
    assert s.survived > 0


def test_empty_suite_scores_nothing():
    s = score_oracle(SRC, "inc", "")
    assert s.total_mutants == 0
    assert s.confidence == "unknown"
    assert s.score is None


def test_no_mutants_for_unknown_function():
    s = score_oracle(SRC, "does_not_exist", "def test(): pass")
    assert s.total_mutants == 0
    assert s.confidence == "unknown"


def test_score_to_dict_shape():
    s = MutationScore(function_name="f", killed=3, survived=1)
    d = s.to_dict()
    assert d["mutation_score"] == 0.75
    assert d["confidence"] == "medium"
    assert d["viable"] == 4


def test_confidence_thresholds():
    assert MutationScore("f", killed=8, survived=2).confidence == "high"   # 0.8
    assert MutationScore("f", killed=5, survived=5).confidence == "medium" # 0.5
    assert MutationScore("f", killed=1, survived=9).confidence == "low"    # 0.1
    assert MutationScore("f").confidence == "unknown"                      # no viable


def test_errored_mutant_counts_as_killed_when_baseline_works():
    """A mutant that turns a clean suite into errors is detected (killed), not
    discarded as not-viable, so data functions get a real confidence."""
    from qallm.verification.mutation_score import score_oracle
    source = (
        "def scale(values, factor):\n"
        "    out = []\n"
        "    for v in values:\n"
        "        out.append(v * factor + 1)\n"
        "    return out\n"
    )
    test = (
        "from source_module import scale\n"
        "def test_basic():\n"
        "    assert scale([1, 2], 2) == [3, 5]\n"
    )
    s = score_oracle(source, "scale", test)
    assert s.total_mutants > 0
    assert s.viable > 0
    assert s.confidence in ("high", "medium", "low")


# --- regression: module name must be derived from the tests' import line ---
# A suite imports the function from a specific module (for example
# `from source_foo_c0 import f`). If the scorer writes the source under a
# different filename, the import fails, every mutant errors, and the suite
# spuriously detects nothing (killed=0, confidence=unknown). These tests pin
# that the derived name keeps the suite live so real kills are counted.


def test_module_name_derived_from_import():
    suite = "from source_reliability_gap_c0 import f\ndef test_x(): pass"
    assert _module_name_from_tests(suite) == "source_reliability_gap_c0"


def test_module_name_none_without_import():
    assert _module_name_from_tests("def test_x(): pass") is None


def test_suite_with_named_import_kills_mutants():
    # The off-by-one is detected only if the suite can import the source under
    # the name it expects. With the derivation, mutants of `f` are killed.
    source = "def f(a, b):\n    return a + b\n"
    suite = (
        "from source_widget_c0 import f\n"
        "def test_add(): assert f(2, 3) == 5\n"
        "def test_zero(): assert f(0, 0) == 0\n"
    )
    score = score_oracle(source, "f", suite)  # module_name auto-derived
    assert score.total_mutants > 0
    assert score.killed > 0
    assert score.confidence != "unknown"
