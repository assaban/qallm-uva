"""Tests for the mutation engine (oracle self-validation)."""

import ast
from qallm.verification.mutation import generate_mutants


def _parses(src):
    ast.parse(src)
    return True


def test_arithmetic_operator_mutated():
    src = "def f(a, b):\n    return a + b\n"
    ms = generate_mutants(src, "f")
    assert any(m.operator == "AOR" for m in ms)
    assert all(_parses(m.source) for m in ms)
    # the + becomes - in at least one mutant
    assert any("a - b" in m.source for m in ms)


def test_comparison_operator_mutated():
    src = "def f(x):\n    return x < 10\n"
    ms = generate_mutants(src, "f")
    assert any(m.operator == "ROR" for m in ms)
    assert any("<=" in m.source for m in ms)


def test_constant_mutated():
    src = "def f(x):\n    return x + 1\n"
    ms = generate_mutants(src, "f")
    assert any(m.operator == "CRP" for m in ms)
    assert any("x + 2" in m.source for m in ms)


def test_return_value_replaced():
    src = "def f(x):\n    return x * 2\n"
    ms = generate_mutants(src, "f")
    assert any(m.operator == "RVR" for m in ms)
    assert any("return None" in m.source for m in ms)


def test_boolean_operator_mutated():
    src = "def f(a, b):\n    return a and b\n"
    ms = generate_mutants(src, "f")
    assert any(m.operator == "COI" for m in ms)
    assert any(" or " in m.source for m in ms)


def test_only_target_function_mutated():
    src = (
        "def target(a, b):\n    return a + b\n\n"
        "def other(a, b):\n    return a + b\n"
    )
    ms = generate_mutants(src, "target")
    # every mutant keeps `other` intact
    for m in ms:
        assert "def other(a, b):\n    return a + b" in m.source


def test_bounded_per_operator():
    src = "def f(a, b, c, d, e):\n    return a + b + c + d + e\n"
    ms = generate_mutants(src, "f", max_per_operator=2)
    aor = [m for m in ms if m.operator == "AOR"]
    assert len(aor) <= 2


def test_unknown_function_yields_nothing():
    assert generate_mutants("def f():\n    return 1\n", "nope") == []


def test_syntax_error_yields_nothing():
    assert generate_mutants("def f(:\n bad", "f") == []


def test_mutants_differ_from_original():
    src = "def f(a, b):\n    return a + b\n"
    for m in generate_mutants(src, "f"):
        assert m.source != src
