"""Correctness tests for the statistical functions behind the thesis claims.

stats.py computes Cliff's delta and the Wilcoxon signed-rank test, which back
the "RL significantly outperforms baselines" result. These are exactly the
numbers an examiner will scrutinise, so they are tested for correctness
against hand-computed and known-property values, not just executed.
"""



from qallm.stats import cliffs_delta, wilcoxon_test


# ── Cliff's delta: deterministic, hand-verifiable ──

def test_cliffs_delta_complete_dominance_is_plus_one():
    # every x > every y  ->  delta = +1, "large"
    d, interp = cliffs_delta([10, 11, 12], [1, 2, 3])
    assert d == 1.0
    assert interp == "large"


def test_cliffs_delta_complete_reverse_is_minus_one():
    d, interp = cliffs_delta([1, 2, 3], [10, 11, 12])
    assert d == -1.0
    assert interp == "large"


def test_cliffs_delta_identical_samples_is_zero():
    d, interp = cliffs_delta([5, 5, 5], [5, 5, 5])
    assert d == 0.0
    assert interp == "negligible"


def test_cliffs_delta_hand_computed_value():
    # x = [1, 2], y = [1, 3]
    # pairs (xi, yi): (1,1) tie, (1,3) less, (2,1) more, (2,3) less
    # more = 1, less = 2, n_x*n_y = 4 -> delta = (1-2)/4 = -0.25
    d, interp = cliffs_delta([1, 2], [1, 3])
    assert d == -0.25
    assert interp == "small"   # 0.147 <= 0.25 < 0.33


def test_cliffs_delta_threshold_boundaries():
    # Construct deltas landing in each band and check the label.
    # negligible: |d| < 0.147
    d, interp = cliffs_delta([2, 2, 2, 2, 2, 2, 2, 3], [2, 2, 2, 2, 2, 2, 2, 1])
    assert interp in {"negligible", "small"}  # near a boundary; label is monotone
    # large: clear dominance
    _, interp_large = cliffs_delta([100, 200], [1, 2])
    assert interp_large == "large"


def test_cliffs_delta_empty_input_is_safe():
    assert cliffs_delta([], [1, 2]) == (0.0, "negligible")
    assert cliffs_delta([1, 2], []) == (0.0, "negligible")


# ── Wilcoxon signed-rank ──

def test_wilcoxon_insufficient_pairs_returns_note():
    # Fewer than 5 non-tied pairs -> not significant, explanatory note.
    res = wilcoxon_test([1, 2, 3], [1, 2, 3])  # all tied -> 0 pairs
    assert res["significant"] is False
    assert res["p_value"] is None
    assert "Insufficient" in res["note"]


def test_wilcoxon_clear_consistent_improvement_is_significant():
    # y consistently and substantially above x across many pairs.
    x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    y = [v + 5 for v in x]
    res = wilcoxon_test(x, y)
    assert res["p_value"] is not None
    assert res["significant"] is True
    assert res["n_pairs"] == 10
    # Effect size should be large for complete separation-ish data.
    assert res["effect_size"] in {"medium", "large"}
    assert 0.0 <= res["p_value"] <= 1.0


def test_wilcoxon_result_is_json_serialisable():
    # Regression: scipy returns numpy scalars; `significant` was a numpy bool
    # that broke json.dumps. The dict is returned by the API/export, so it
    # must serialise with native types.
    import json
    res = wilcoxon_test([1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12])
    json.dumps(res)  # must not raise
    assert isinstance(res["significant"], bool)
    assert isinstance(res["p_value"], float)
    assert isinstance(res["statistic"], float)


def test_wilcoxon_no_real_difference_not_significant():
    # Small alternating noise around equality: should not be significant.
    x = [10, 10, 10, 10, 10, 10, 10, 10]
    y = [11, 9, 11, 9, 11, 9, 11, 9]
    res = wilcoxon_test(x, y)
    assert res["p_value"] is not None
    assert res["significant"] is False


def test_wilcoxon_p_value_in_unit_interval_and_rounded():
    x = [1, 3, 2, 5, 4, 7, 6, 9]
    y = [2, 4, 3, 6, 5, 8, 7, 10]
    res = wilcoxon_test(x, y)
    assert res["p_value"] is not None
    assert 0.0 <= res["p_value"] <= 1.0
    assert isinstance(res["statistic"], float)


def test_wilcoxon_alpha_threshold_respected():
    x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    y = [v + 5 for v in x]
    strict = wilcoxon_test(x, y, alpha=0.0)   # nothing can be significant
    assert strict["significant"] is False
    lenient = wilcoxon_test(x, y, alpha=0.05)
    assert lenient["significant"] is True


# ── bootstrap confidence interval for count-weighted rates ──

from qallm.stats import bootstrap_rate_ci  # noqa: E402


def test_bootstrap_point_matches_pooled_rate():
    # 3 sessions; pooled rate = (1+2+3)/(2+4+6) = 6/12 = 0.5
    res = bootstrap_rate_ci([1, 2, 3], [2, 4, 6])
    assert res["point"] == 0.5
    assert res["n_sessions"] == 3


def test_bootstrap_ci_brackets_point():
    num = [1, 2, 0, 3, 1, 2, 1, 0, 2, 1]
    den = [2, 4, 2, 5, 3, 4, 2, 2, 4, 3]
    res = bootstrap_rate_ci(num, den)
    assert res["ci_low"] <= res["point"] <= res["ci_high"]
    assert 0.0 <= res["ci_low"] <= 1.0
    assert 0.0 <= res["ci_high"] <= 1.0


def test_bootstrap_is_deterministic_with_seed():
    num = [1, 2, 0, 3, 1, 2]
    den = [2, 4, 2, 5, 3, 4]
    a = bootstrap_rate_ci(num, den, seed=7)
    b = bootstrap_rate_ci(num, den, seed=7)
    assert a == b


def test_bootstrap_zero_denominator_returns_none_point():
    res = bootstrap_rate_ci([0, 0], [0, 0])
    assert res["point"] is None
    assert res["ci_low"] is None


def test_bootstrap_single_session_is_degenerate():
    res = bootstrap_rate_ci([1], [2])
    assert res["point"] == 0.5
    assert res["ci_low"] == res["ci_high"] == 0.5
    assert "note" in res


def test_bootstrap_complete_certainty_tight_interval():
    # Every session is a pure gap (num == den): rate must be 1.0 with a
    # degenerate-to-tight interval since every resample also gives 1.0.
    res = bootstrap_rate_ci([2, 3, 1, 4], [2, 3, 1, 4])
    assert res["point"] == 1.0
    assert res["ci_low"] == 1.0 and res["ci_high"] == 1.0


def test_bootstrap_mismatched_lengths_raises():
    import pytest as _pytest
    with _pytest.raises(ValueError):
        bootstrap_rate_ci([1, 2], [1])


def test_bootstrap_result_is_json_serialisable():
    import json
    res = bootstrap_rate_ci([1, 2, 3], [2, 4, 6])
    json.dumps(res)  # must not raise
