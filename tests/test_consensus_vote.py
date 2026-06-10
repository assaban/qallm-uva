"""Tests for assertion-level majority voting (consensus_vote)."""

from qallm.verification.consensus_vote import (
    majority_expected,
    drop_outvoted_assertions,
)


def test_majority_wins_over_minority():
    samples = [
        "def t(): assert f(2) == 6",
        "def t(): assert f(2) == 6",
        "def t(): assert f(2) == 4",  # minority, wrong
    ]
    winners = majority_expected(samples, "f")
    # one call has a winner
    assert len(winners) == 1
    # the wrong-value sample gets its assert pruned
    pruned = drop_outvoted_assertions(samples[2], "f", winners)
    assert "== 4" not in pruned
    assert "pass" in pruned


def test_majority_keeps_winning_assertions():
    samples = [
        "def t(): assert f(2) == 6",
        "def t(): assert f(2) == 6",
    ]
    winners = majority_expected(samples, "f")
    kept = drop_outvoted_assertions(samples[0], "f", winners)
    # No disagreement (single value), so nothing is a "winner over a loser";
    # the assertion is preserved either way.
    assert "== 6" in kept


def test_tie_produces_no_winner():
    samples = [
        "def t(): assert f(2) == 6",
        "def t(): assert f(2) == 4",
    ]
    winners = majority_expected(samples, "f")
    # 1 vs 1 is not a strict majority.
    assert winners == {}


def test_ballot_stuffing_prevented():
    # One sample repeats the same wrong assertion many times; it still counts
    # once, so the single correct sample is not outvoted into a tie.
    samples = [
        "def t():\n    assert f(2) == 4\n    assert f(2) == 4\n    assert f(2) == 4",
        "def t(): assert f(2) == 6",
        "def t(): assert f(2) == 6",
    ]
    winners = majority_expected(samples, "f")
    # 6 has 2 sample-votes, 4 has 1 sample-vote -> 6 wins.
    assert len(winners) == 1
    pruned = drop_outvoted_assertions(samples[0], "f", winners)
    assert "== 4" not in pruned


def test_approx_normalised():
    samples = [
        "def t(): assert f(2) == pytest.approx(3.0)",
        "def t(): assert f(2) == pytest.approx(3.0)",
        "def t(): assert f(2) == pytest.approx(9.9)",
    ]
    winners = majority_expected(samples, "f")
    assert len(winners) == 1  # 3.0 wins over 9.9


def test_raises_and_inequalities_untouched():
    # Non-equality oracles are not voted on and never pruned.
    samples = [
        "def t():\n    with pytest.raises(ValueError):\n        f(-1)",
        "def t():\n    with pytest.raises(ValueError):\n        f(-1)",
    ]
    winners = majority_expected(samples, "f")
    assert winners == {}
    kept = drop_outvoted_assertions(samples[0], "f", winners)
    assert "pytest.raises(ValueError)" in kept


def test_only_votes_on_function_under_test():
    # An assertion on a helper (not the function under test) is ignored.
    samples = [
        "def t(): assert helper(2) == 99",
        "def t(): assert helper(2) == 1",
    ]
    winners = majority_expected(samples, "f")
    assert winners == {}


def test_unparseable_source_passthrough():
    assert drop_outvoted_assertions("def (((", "f", {"k": "v"}) == "def ((("
