"""AST validation of generated test code before it is executed.

A language model sometimes writes a test that takes a parameter it never
provides a fixture for, e.g.::

    def test_complex_dictionary_input(fixed_obj):   # <- no such fixture
        ...

pytest treats every test-function parameter as a fixture request. With no
matching fixture, the test errors during *setup* and never runs, producing
no verification signal (this is the ``fixed_obj`` case seen on the
``domain.py`` sample, where every ``dangerous`` test errored). Catching this
before execution lets the pipeline drop or repair the offending tests and
report how many were invalid, so the verification signal is not silently
polluted by tests that never ran.

The check is deliberately conservative. It flags exactly one thing: a test
function whose parameter is neither a fixture defined in the same module nor
a known pytest builtin fixture. It does not try to flag undefined names in
test bodies, because the executor injects the source module via
``from <module> import *`` at run time, so a free name may well be a valid
source export that is simply not visible in the test text alone. Flagging
those would risk discarding good tests; flagging unsatisfied fixtures does
not.
"""

from __future__ import annotations

import ast

# Fixtures pytest (and common plugins) provide without any definition in
# the test module. A parameter with one of these names is always
# satisfiable, so it must never be flagged.
PYTEST_BUILTIN_FIXTURES: frozenset[str] = frozenset({
    # pytest core
    "request", "tmp_path", "tmp_path_factory", "tmpdir", "tmpdir_factory",
    "capsys", "capsysbinary", "capfd", "capfdbinary", "caplog",
    "monkeypatch", "recwarn", "pytestconfig", "record_property",
    "record_testsuite_property", "cache", "doctest_namespace",
    "testdir", "pytester",
    # pytest-asyncio
    "event_loop", "event_loop_policy",
    # pytest-mock
    "mocker",
})

# A parameter named ``self`` or ``cls`` is a method receiver, not a fixture.
_RECEIVER_PARAMS: frozenset[str] = frozenset({"self", "cls"})


def _collect_defined_fixtures(tree: ast.Module) -> set[str]:
    """Return names of functions decorated as pytest fixtures in the module.

    Recognises ``@pytest.fixture``, ``@pytest.fixture(...)``, ``@fixture``
    and ``@fixture(...)`` (the latter from ``from pytest import fixture``).
    """
    fixtures: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            # @pytest.fixture / @<anything>.fixture
            if isinstance(target, ast.Attribute) and target.attr == "fixture":
                fixtures.add(node.name)
                break
            # @fixture
            if isinstance(target, ast.Name) and target.id == "fixture":
                fixtures.add(node.name)
                break
    return fixtures


def _test_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Top-level functions whose names start with ``test``."""
    out: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name.startswith("test"):
            out.append(node)
    return out


def _params_with_parametrize(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Parameter names supplied by ``@pytest.mark.parametrize`` decorators.

    Those are provided by the decorator, not by a fixture, so they must not
    be flagged. The first argument of parametrize is a names string (or a
    sequence of names); we parse both forms.
    """
    supplied: set[str] = set()
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        func = dec.func
        is_parametrize = (
            isinstance(func, ast.Attribute) and func.attr == "parametrize"
        )
        if not is_parametrize or not dec.args:
            continue
        first = dec.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            for piece in first.value.replace(",", " ").split():
                supplied.add(piece)
        elif isinstance(first, (ast.List, ast.Tuple)):
            for elt in first.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    supplied.add(elt.value)
    return supplied


def find_unsatisfied_fixtures(code: str) -> dict[str, list[str]]:
    """Map each test function to the parameter names it requests but that no
    fixture (defined or builtin) and no parametrize decorator provides.

    Returns an empty dict when everything is satisfiable. Raises nothing on
    a syntax error: it returns an empty dict, leaving syntax checks to the
    caller's existing ``compile`` step.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}

    defined = _collect_defined_fixtures(tree)
    available = defined | PYTEST_BUILTIN_FIXTURES

    problems: dict[str, list[str]] = {}
    for fn in _test_functions(tree):
        parametrized = _params_with_parametrize(fn)
        args = fn.args
        # positional-or-keyword and positional-only parameters can be
        # fixture requests; *args/**kwargs and keyword-only are not how
        # fixtures are injected, so we ignore them.
        candidate_params = [a.arg for a in (args.posonlyargs + args.args)]
        unsatisfied = [
            p for p in candidate_params
            if p not in available
            and p not in parametrized
            and p not in _RECEIVER_PARAMS
        ]
        if unsatisfied:
            problems[fn.name] = unsatisfied
    return problems


def strip_unsatisfied_fixture_tests(code: str) -> tuple[str, list[str]]:
    """Remove test functions that request unsatisfiable fixtures.

    Returns the rewritten code and the list of removed test names. Keeps
    every other top-level statement (imports, fixtures, helpers, valid
    tests) intact. If parsing fails or nothing needs removing, returns the
    code unchanged with an empty list.
    """
    problems = find_unsatisfied_fixtures(code)
    if not problems:
        return code, []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code, []

    to_remove = set(problems.keys())
    kept_body = [
        node for node in tree.body
        if not (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in to_remove
        )
    ]
    tree.body = kept_body
    try:
        rewritten = ast.unparse(tree)
    except Exception:  # noqa: BLE001 - unparse should not fail, but be safe
        return code, []
    return rewritten, sorted(to_remove)
