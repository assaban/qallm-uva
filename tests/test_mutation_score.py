"""Tests for mutation-based oracle confidence scoring."""

from qallm.verification.mutation_score import score_oracle, MutationScore


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
