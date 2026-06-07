"""Tests for incoherent-oracle detection (false-BUG prevention).

A generated test that feeds the function under test one input but its oracle
helper a different input produces a failure that is an artifact of the test,
not a defect in the code. These must be dropped before execution so they do
not inflate QALLM's bug counts. The conservative requirement is paramount:
legitimate tests must never be flagged.
"""

from qallm.verification.test_validator import (
    find_incoherent_oracle_tests,
    strip_incoherent_oracle_tests,
)

FUT = "complex_branching"


# ── must FLAG (genuinely incoherent) ──

def test_flags_intermediate_variable_mismatch():
    code = (
        "def _expected_total(n):\n    return n\n"
        "def test_large():\n"
        "    n = 1000\n"
        "    result = complex_branching(n)\n"
        "    assert result == _expected_total(100)\n"
    )
    flagged = find_incoherent_oracle_tests(code, FUT)
    assert "test_large" in flagged
    assert flagged["test_large"] == (1000, 100)


def test_flags_inline_mismatch():
    code = (
        "def _expected_total(n):\n    return n\n"
        "def test_x():\n"
        "    assert complex_branching(1000) == _expected_total(100)\n"
    )
    assert "test_x" in find_incoherent_oracle_tests(code, FUT)


def test_strip_removes_only_the_incoherent_test():
    code = (
        "def _expected_total(n):\n    return n\n"
        "def test_good():\n"
        "    assert complex_branching(10) == _expected_total(10)\n"
        "def test_bad():\n"
        "    assert complex_branching(1000) == _expected_total(100)\n"
    )
    rewritten, removed = strip_incoherent_oracle_tests(code, FUT)
    assert removed == ["test_bad"]
    assert "def test_good" in rewritten
    assert "def test_bad" not in rewritten
    assert "def _expected_total" in rewritten   # helper preserved


# ── must NOT flag (legitimate) ──

def test_same_literal_is_fine():
    code = (
        "def _expected_total(n):\n    return n\n"
        "def test_small():\n"
        "    assert complex_branching(10) == _expected_total(10)\n"
    )
    assert find_incoherent_oracle_tests(code, FUT) == {}


def test_same_variable_both_sides_is_fine():
    code = (
        "def _expected_total(n):\n    return n\n"
        "def test_n():\n"
        "    n = 31\n"
        "    assert complex_branching(n) == _expected_total(n)\n"
    )
    assert find_incoherent_oracle_tests(code, FUT) == {}


def test_weak_assertion_no_oracle_is_fine():
    code = (
        "def test_large():\n"
        "    result = complex_branching(1000)\n"
        "    assert result >= 0\n"
    )
    assert find_incoherent_oracle_tests(code, FUT) == {}


def test_unrelated_production_function_not_treated_as_oracle():
    # decode_len is NOT defined in the test module, so it is not an oracle
    # helper; different inputs to two production functions are legitimate.
    code = (
        "def test_two():\n"
        "    assert encode(5) == decode_len(10)\n"
    )
    assert find_incoherent_oracle_tests(code, "encode") == {}


def test_no_helpers_means_nothing_flagged():
    code = (
        "def test_a():\n"
        "    assert complex_branching(10) == 19\n"
    )
    assert find_incoherent_oracle_tests(code, FUT) == {}


def test_non_constant_inputs_are_not_flagged():
    # If inputs are not simple constants we cannot prove incoherence; leave it.
    code = (
        "def _expected_total(n):\n    return n\n"
        "def test_dyn(some_value):\n"
        "    assert complex_branching(some_value) == _expected_total(some_value * 2)\n"
    )
    assert find_incoherent_oracle_tests(code, FUT) == {}


def test_syntax_error_is_safe():
    code = "def test_broken(:\n    pass\n"
    rewritten, removed = strip_incoherent_oracle_tests(code, FUT)
    assert rewritten == code and removed == []


def test_no_change_returns_original():
    code = (
        "def _expected_total(n):\n    return n\n"
        "def test_ok():\n"
        "    assert complex_branching(5) == _expected_total(5)\n"
    )
    rewritten, removed = strip_incoherent_oracle_tests(code, FUT)
    assert removed == [] and rewritten == code
