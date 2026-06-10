"""Assertion-level majority voting for consensus test generation.

The union merge (keep every sample's tests) maximises recall but lets a single
sample's wrong expected value survive, producing a false positive on correct
code (observed on the lab `cryptic` function, whose vague docstring made the
oracle guess). Majority voting addresses that: for each distinct call under
test, collect the expected value each sample asserts, and keep an assertion
only if a majority of the samples that tested that call agree on the value. A
one-off wrong expected value is outvoted and dropped.

This operates on simple, common assertion forms:
    assert func(args) == EXPECTED
    assert func(args) is EXPECTED        (None/True/False)
    assert func(args) == pytest.approx(EXPECTED)

Assertions that do not match these forms (raises, inequalities, multi-statement
oracles) are passed through unchanged; voting only prunes the equality oracles,
where a disagreement is meaningful.
"""

from __future__ import annotations

import ast
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def _expected_key(node: ast.expr) -> str | None:
    """A stable string for the expected-value side of an equality assert.

    Returns None when the expected value is not a literal/simple expression we
    can compare across samples (e.g. it references a helper), in which case the
    assertion is not voted on.
    """
    try:
        return ast.dump(node, annotate_fields=False)
    except Exception:
        return None


def _call_key(node: ast.expr, func_name: str) -> str | None:
    """A stable string for a call to the function under test, or None.

    Only calls to ``func_name`` are keyed; other calls are ignored so we do not
    vote across unrelated helpers.
    """
    if not isinstance(node, ast.Call):
        return None
    target = node.func
    name = getattr(target, "id", None) or getattr(target, "attr", None)
    if name != func_name:
        return None
    try:
        return ast.dump(node, annotate_fields=False)
    except Exception:
        return None


def _equality_assert(stmt: ast.stmt, func_name: str) -> tuple[str, str] | None:
    """If stmt is `assert <call to func> == <expected>` (or is/approx), return
    (call_key, expected_key); else None."""
    if not isinstance(stmt, ast.Assert):
        return None
    test = stmt.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None
    if not isinstance(test.ops[0], (ast.Eq, ast.Is)):
        return None

    left, right = test.left, test.comparators[0]
    # The call may be on either side; the expected value is the other side.
    call_key = _call_key(left, func_name)
    expected_node = right
    if call_key is None:
        call_key = _call_key(right, func_name)
        expected_node = left
    if call_key is None:
        return None

    # Unwrap pytest.approx(...) so approx(3.0) and approx(3.0) compare equal.
    if (isinstance(expected_node, ast.Call)
            and getattr(expected_node.func, "attr", None) == "approx"
            and expected_node.args):
        expected_node = expected_node.args[0]

    expected_key = _expected_key(expected_node)
    if expected_key is None:
        return None
    return call_key, expected_key


def majority_expected(
    sample_sources: list[str], func_name: str
) -> dict[str, str]:
    """For each call to func_name, the expected-value key a majority asserts.

    Returns {call_key: winning_expected_key}. A call with no majority (tie or
    all distinct) is omitted, its assertions are then treated as unvoted and
    kept by the caller, since we cannot say which value is wrong.
    """
    # call_key -> expected_key -> number of SAMPLES asserting it
    votes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for src in sample_sources:
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        seen_in_sample: set[tuple[str, str]] = set()
        for node in ast.walk(tree):
            pair = _equality_assert(node, func_name)
            if pair is None:
                continue
            # Count each (call, expected) at most once per sample, so a sample
            # repeating an assertion does not stuff the ballot.
            if pair in seen_in_sample:
                continue
            seen_in_sample.add(pair)
            call_key, expected_key = pair
            votes[call_key][expected_key] += 1

    winners: dict[str, str] = {}
    for call_key, tally in votes.items():
        total = sum(tally.values())
        top_value, top_count = max(tally.items(), key=lambda kv: kv[1])
        # Strict majority of the samples that tested this call.
        if top_count * 2 > total and len(tally) > 1:
            winners[call_key] = top_value
            losers = [v for v in tally if v != top_value]
            logger.info(
                "Consensus vote on %s: kept %d/%d for a call, dropped minority "
                "value(s) %s", func_name, top_count, total, losers,
            )
    return winners


def drop_outvoted_assertions(
    test_source: str, func_name: str, winners: dict[str, str]
) -> str:
    """Remove asserts whose expected value lost the majority vote.

    Only assertions on a call that HAS a majority winner and whose expected
    value differs from it are removed. Everything else (unvoted calls, raises,
    inequalities, the winning assertions) is preserved. Returns the source
    unchanged if it does not parse.
    """
    if not winners:
        return test_source
    try:
        tree = ast.parse(test_source)
    except SyntaxError:
        return test_source

    class _Pruner(ast.NodeTransformer):
        def visit_Assert(self, node: ast.Assert):
            pair = _equality_assert(node, func_name)
            if pair is None:
                return node
            call_key, expected_key = pair
            win = winners.get(call_key)
            if win is not None and win != expected_key:
                # Drop this assert: it asserts a minority (likely wrong) value.
                return None
            return node

    pruned = _Pruner().visit(tree)
    ast.fix_missing_locations(pruned)
    # Guard: a test function whose body becomes empty would be a SyntaxError.
    for node in ast.walk(pruned):
        if isinstance(node, ast.FunctionDef) and not node.body:
            node.body = [ast.Pass()]
    try:
        return ast.unparse(pruned)
    except Exception:
        return test_source
