"""Tests for AST validation of generated tests (undefined fixtures)."""

from qallm.verification.test_validator import (
    find_unsatisfied_fixtures,
    strip_unsatisfied_fixture_tests,
)


def test_flags_undefined_fixture():
    code = '''
def test_uses_missing(fixed_obj):
    assert fixed_obj == 1
'''
    problems = find_unsatisfied_fixtures(code)
    assert problems == {"test_uses_missing": ["fixed_obj"]}


def test_defined_fixture_is_ok():
    code = '''
import pytest

@pytest.fixture
def fixed_obj():
    return 1

def test_uses_defined(fixed_obj):
    assert fixed_obj == 1
'''
    assert find_unsatisfied_fixtures(code) == {}


def test_bare_fixture_decorator_is_ok():
    code = '''
from pytest import fixture

@fixture
def thing():
    return 7

def test_thing(thing):
    assert thing == 7
'''
    assert find_unsatisfied_fixtures(code) == {}


def test_pytest_builtin_fixtures_are_ok():
    code = '''
def test_with_tmp(tmp_path, monkeypatch, capsys):
    assert tmp_path is not None
'''
    assert find_unsatisfied_fixtures(code) == {}


def test_parametrize_params_are_ok():
    code = '''
import pytest

@pytest.mark.parametrize("value,expected", [(1, 2), (2, 3)])
def test_param(value, expected):
    assert value + 1 == expected
'''
    assert find_unsatisfied_fixtures(code) == {}


def test_no_arg_tests_are_ok():
    code = '''
def test_simple():
    assert 1 + 1 == 2
'''
    assert find_unsatisfied_fixtures(code) == {}


def test_free_names_in_body_not_flagged():
    # `dangerous` would arrive via `from <module> import *` at runtime; the
    # validator must not flag body names, only unsatisfied parameters.
    code = '''
def test_calls_source():
    result = dangerous("1 + 1")
    assert result is not None
'''
    assert find_unsatisfied_fixtures(code) == {}


def test_strip_removes_only_offending_tests():
    code = '''
import pytest

@pytest.fixture
def good():
    return 1

def test_ok(good):
    assert good == 1

def test_bad(fixed_obj):
    assert fixed_obj == 2

def test_also_ok():
    assert True
'''
    rewritten, removed = strip_unsatisfied_fixture_tests(code)
    assert removed == ["test_bad"]
    assert "test_ok" in rewritten
    assert "test_also_ok" in rewritten
    assert "test_bad" not in rewritten
    # The kept code still parses and the good fixture survived.
    assert "def good" in rewritten
    compile(rewritten, "<rewritten>", "exec")


def test_strip_noop_when_all_valid():
    code = '''
def test_a():
    assert True
'''
    rewritten, removed = strip_unsatisfied_fixture_tests(code)
    assert removed == []
    assert rewritten == code


def test_syntax_error_returns_empty():
    code = "def test_broken(:\n    pass"
    assert find_unsatisfied_fixtures(code) == {}
    rewritten, removed = strip_unsatisfied_fixture_tests(code)
    assert removed == []


def test_multiple_unsatisfied_params():
    code = '''
def test_two(foo, bar):
    assert foo == bar
'''
    problems = find_unsatisfied_fixtures(code)
    assert set(problems["test_two"]) == {"foo", "bar"}
