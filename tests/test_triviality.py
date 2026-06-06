"""Tests for the triviality detector (skipping non-analyzable units)."""

from qallm.ingestion.triviality import assess_triviality


# ── trivial cases (should be skipped) ──

def test_empty_string():
    assert assess_triviality("").is_trivial


def test_whitespace_only():
    assert assess_triviality("   \n\n  \t\n").is_trivial


def test_comment_only():
    assert assess_triviality("# just a comment\n# another\n").is_trivial


def test_module_docstring_only():
    assert assess_triviality('"""A package."""\n').is_trivial


def test_import_only_init():
    src = "from .core import Thing\nimport os\n"
    assert assess_triviality(src).is_trivial


def test_all_declaration_only():
    src = '"""pkg."""\nfrom .x import A, B\n__all__ = ["A", "B"]\n'
    assert assess_triviality(src).is_trivial


def test_dunder_version_only():
    src = '__version__ = "1.0.0"\n__author__ = "x"\n'
    assert assess_triviality(src).is_trivial


def test_pass_and_ellipsis():
    assert assess_triviality("pass\n").is_trivial
    assert assess_triviality("...\n").is_trivial


# ── non-trivial cases (must be kept) ──

def test_function_kept():
    assert not assess_triviality("def f():\n    return 1\n").is_trivial


def test_class_kept():
    assert not assess_triviality("class C:\n    pass\n").is_trivial


def test_executable_statement_kept():
    # A real call at module level is logic worth analyzing.
    assert not assess_triviality("print('hi')\n").is_trivial


def test_loop_kept():
    assert not assess_triviality("for i in range(3):\n    print(i)\n").is_trivial


def test_real_assignment_kept():
    # Non-dunder computed assignment is logic.
    assert not assess_triviality("x = compute() + 1\n").is_trivial


def test_conditional_kept():
    assert not assess_triviality("if True:\n    do()\n").is_trivial


def test_all_with_function_kept():
    src = '"""pkg."""\n__all__ = ["f"]\ndef f():\n    return 1\n'
    assert not assess_triviality(src).is_trivial


# ── syntax errors must NOT be skipped ──

def test_syntax_error_is_kept():
    res = assess_triviality("def broken(:\n    pass\n")
    assert not res.is_trivial
    assert "parse" in res.reason.lower()


# ── reason is populated for auditability ──

def test_reason_present_for_trivial():
    assert assess_triviality("").reason
    assert assess_triviality("import os\n").reason
