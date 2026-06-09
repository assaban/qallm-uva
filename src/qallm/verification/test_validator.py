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


# ── Incoherent-oracle detection ──────────────────────────────────────────
#
# A generated test can run without error yet assert something meaningless,
# the most common form being an oracle evaluated at a different input than the
# function under test (FUT). For example:
#
#     def test_large():
#         n = 1000
#         result = complex_branching(n)
#         assert result == _expected_total(100)   # oracle uses 100, not n=1000
#
# This produces a *false* BUG: a failure that is an artifact of the test, not a
# defect in the code. That directly threatens the validity of QALLM's
# execution-based verdicts (a reported bug must be a property of the code, not
# of a malformed test). We therefore detect and drop such tests before they
# run, deterministically and conservatively.
#
# Conservatism is the priority: we flag ONLY the unambiguous case where, in a
# single equality/inequality comparison, the FUT is invoked (directly, or via a
# local variable assigned from a FUT call) with one constant input, and a
# module-local oracle helper is invoked with a DIFFERENT constant input. We do
# not attempt to judge whether an expected literal value is "correct" in
# general (undecidable, and would risk discarding good tests). Unrelated
# production functions are not treated as oracles, only helpers defined in the
# test module itself.


def _module_local_oracle_helpers(tree: ast.Module, fut_name: str) -> set[str]:
    """Module-local functions that look like oracle helpers.

    Any function defined at module level in the test file that is neither the
    function under test nor a test_* function is a candidate oracle helper
    (commonly a ``_expected_*`` reimplementation of the expected result).
    """
    helpers: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name != fut_name and not node.name.startswith("test_"):
                helpers.add(node.name)
    return helpers


def _first_arg_literal(call: ast.Call, const_binds: dict[str, object]) -> object | None:
    """The first positional argument of ``call`` as a constant, if knowable.

    Resolves a direct literal, or a local variable previously bound to a
    literal. Returns None when the argument is not a simple constant (so we
    only ever compare known-constant against known-constant).
    """
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Constant):
        return arg.value
    if isinstance(arg, ast.Name) and arg.id in const_binds:
        return const_binds[arg.id]
    return None


def find_incoherent_oracle_tests(code: str, fut_name: str) -> dict[str, tuple[object, object]]:
    """Map test name -> (fut_input, oracle_input) for incoherent-oracle tests.

    A test is incoherent when, in one comparison, the function under test is
    fed one constant input and a module-local oracle helper is fed a different
    constant input. Only such tests are returned; everything else is left for
    execution to judge.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}

    oracle_helpers = _module_local_oracle_helpers(tree, fut_name)
    if not oracle_helpers:
        return {}

    flagged: dict[str, tuple[object, object]] = {}
    for fn in tree.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not fn.name.startswith("test_"):
            continue

        const_binds: dict[str, object] = {}
        fut_arg_of: dict[str, object] = {}  # local var -> FUT input that produced it
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name):
                target = node.targets[0].id
                value = node.value
                if isinstance(value, ast.Constant):
                    const_binds[target] = value.value
                elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name) \
                        and value.func.id == fut_name:
                    lit = _first_arg_literal(value, const_binds)
                    if lit is not None:
                        fut_arg_of[target] = lit

        for cmp in ast.walk(fn):
            if not isinstance(cmp, ast.Compare):
                continue
            fut_inputs: set[object] = set()
            oracle_inputs: set[object] = set()
            for operand in [cmp.left, *cmp.comparators]:
                if isinstance(operand, ast.Call) and isinstance(operand.func, ast.Name):
                    if operand.func.id == fut_name:
                        lit = _first_arg_literal(operand, const_binds)
                        if lit is not None:
                            fut_inputs.add(lit)
                    elif operand.func.id in oracle_helpers:
                        lit = _first_arg_literal(operand, const_binds)
                        if lit is not None:
                            oracle_inputs.add(lit)
                elif isinstance(operand, ast.Name) and operand.id in fut_arg_of:
                    fut_inputs.add(fut_arg_of[operand.id])
            mismatches = [(f, o) for f in fut_inputs for o in oracle_inputs if f != o]
            if mismatches:
                flagged[fn.name] = mismatches[0]
                break

    return flagged


def strip_incoherent_oracle_tests(code: str, fut_name: str) -> tuple[str, list[str]]:
    """Remove tests whose oracle is evaluated at a different input than the FUT.

    Same contract as ``strip_unsatisfied_fixture_tests``: returns the rewritten
    code and the sorted list of removed test names, preserving every other
    top-level statement. Returns the code unchanged on parse failure or when
    nothing needs removing.
    """
    flagged = find_incoherent_oracle_tests(code, fut_name)
    if not flagged:
        return code, []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code, []

    to_remove = set(flagged.keys())
    tree.body = [
        node for node in tree.body
        if not (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in to_remove
        )
    ]
    try:
        rewritten = ast.unparse(tree)
    except Exception:  # noqa: BLE001 - unparse should not fail, but be safe
        return code, []
    return rewritten, sorted(to_remove)


def strip_tests_by_name(code: str, names: set[str]) -> tuple[str, list[str]]:
    """Remove the named top-level test functions, keeping everything else.

    Used by the baseline gate: tests that fail against the original (known
    reference) code are not valid bug-detectors and are stripped before the
    suite is allowed to indict a variant. Returns the rewritten code and the
    sorted list of removed names; returns the code unchanged on parse failure
    or when ``names`` is empty.
    """
    if not names:
        return code, []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code, []

    before = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in names
    }
    if not before:
        return code, []
    tree.body = [
        node for node in tree.body
        if not (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in names
        )
    ]
    try:
        rewritten = ast.unparse(tree)
    except Exception:  # noqa: BLE001 - unparse should not fail, but be safe
        return code, []
    return rewritten, sorted(before)
