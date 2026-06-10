"""Mutation-based self-validation of the verification oracle.

The verification gap rests on a claim a reviewer will attack first: "how do you
know an execution-found bug is a real defect and not an artifact of a flaky
LLM-generated test?" Every existing guard is NEGATIVE, it removes bad tests
(incoherent oracles, baseline-failing tests). None gives POSITIVE evidence that
a test suite is actually a sensitive detector.

Mutation testing is the standard answer in software-testing research. Inject
small, semantics-changing faults into the function under test and check whether
the suite catches each one. A suite that kills the injected mutants has
demonstrated discriminating power, so its verdict on the real code is
trustworthy; a suite that kills none cannot be trusted to have found a real bug.

This module produces mutants of a single target function via AST rewriting,
using classic, well-understood mutation operators. The caller runs the existing
test suite against each mutant (via run_tests) and computes a mutation score
(killed / viable). That score becomes a CONFIDENCE for the gap finding: a bug
reported by a suite with a high mutation score is far more credible than one
from a suite that lets every mutant through.

Operators (conservative, semantics-changing, syntactically safe):
  AOR  arithmetic operator replacement   + <-> -,  * <-> /
  ROR  relational operator replacement   < <-> <=, > <-> >=, == <-> !=
  COI  conditional (boolean) inversion    and <-> or,  not insertion on tests
  CRP  constant replacement               n -> n+1, 0 -> 1, True <-> False
  RVR  return value replacement           return X -> return None (where safe)

Each operator yields at most a bounded number of mutants so the cost stays
proportional to the function size, not exponential.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Mutant:
    """A single mutated version of the target function."""
    operator: str          # e.g. "AOR", "ROR"
    description: str        # human-readable, e.g. "+ -> - at line 3"
    source: str            # full module source with the mutation applied


_ARITH_SWAP = {
    ast.Add: ast.Sub, ast.Sub: ast.Add,
    ast.Mult: ast.Div, ast.Div: ast.Mult,
}
_COMPARE_SWAP = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt,
    ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
}
_BOOL_SWAP = {ast.And: ast.Or, ast.Or: ast.And}


def _target_function(tree: ast.Module, func_name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return node
    return None


def _render(tree: ast.Module) -> str | None:
    try:
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
    except Exception:
        return None


def _collect_nodes(func: ast.FunctionDef, predicate) -> list[ast.AST]:
    return [n for n in ast.walk(func) if predicate(n)]


def generate_mutants(
    source: str, func_name: str, max_per_operator: int = 3
) -> list[Mutant]:
    """Produce semantics-changing mutants of ``func_name`` in ``source``.

    Each mutant changes exactly one operator/constant/return in the target
    function, leaving the rest of the module intact. Returns at most
    max_per_operator mutants per operator class to bound cost. Mutants that do
    not render to valid source are skipped.
    """
    try:
        base = ast.parse(source)
    except SyntaxError:
        return []
    if _target_function(base, func_name) is None:
        return []

    mutants: list[Mutant] = []

    def _apply(make_mutation, operator: str, describe) -> None:
        """Re-parse a fresh tree, locate the i-th candidate node, mutate it,
        render, and record. Re-parsing per mutant keeps mutations independent.
        """
        count = 0
        # Determine how many candidate sites exist on a throwaway parse.
        probe = _target_function(ast.parse(source), func_name)
        sites = make_mutation.collect(probe)
        for idx in range(len(sites)):
            if count >= max_per_operator:
                break
            fresh = ast.parse(source)
            target = _target_function(fresh, func_name)
            node = make_mutation.collect(target)[idx]
            desc = describe(node)
            if not make_mutation.mutate(node):
                continue
            rendered = _render(fresh)
            if rendered is None or rendered == source:
                continue
            mutants.append(Mutant(operator, desc, rendered))
            count += 1

    # AOR: arithmetic operator replacement
    class _AOR:
        @staticmethod
        def collect(fn):
            return [n for n in ast.walk(fn)
                    if isinstance(n, ast.BinOp) and type(n.op) in _ARITH_SWAP]
        @staticmethod
        def mutate(node):
            node.op = _ARITH_SWAP[type(node.op)]()
            return True
    _apply(_AOR, "AOR",
           lambda n: f"arithmetic operator at line {getattr(n, 'lineno', '?')}")

    # ROR: relational operator replacement
    class _ROR:
        @staticmethod
        def collect(fn):
            out = []
            for n in ast.walk(fn):
                if isinstance(n, ast.Compare) and len(n.ops) == 1 and type(n.ops[0]) in _COMPARE_SWAP:
                    out.append(n)
            return out
        @staticmethod
        def mutate(node):
            node.ops[0] = _COMPARE_SWAP[type(node.ops[0])]()
            return True
    _apply(_ROR, "ROR",
           lambda n: f"comparison at line {getattr(n, 'lineno', '?')}")

    # COI: boolean operator swap (and <-> or)
    class _COI:
        @staticmethod
        def collect(fn):
            return [n for n in ast.walk(fn)
                    if isinstance(n, ast.BoolOp) and type(n.op) in _BOOL_SWAP]
        @staticmethod
        def mutate(node):
            node.op = _BOOL_SWAP[type(node.op)]()
            return True
    _apply(_COI, "COI",
           lambda n: f"boolean operator at line {getattr(n, 'lineno', '?')}")

    # CRP: constant replacement (numbers and booleans)
    class _CRP:
        @staticmethod
        def collect(fn):
            out = []
            for n in ast.walk(fn):
                if isinstance(n, ast.Constant) and isinstance(n.value, (int, float, bool)):
                    out.append(n)
            return out
        @staticmethod
        def mutate(node):
            v = node.value
            if isinstance(v, bool):
                node.value = not v
            elif isinstance(v, int):
                node.value = v + 1
            elif isinstance(v, float):
                node.value = v + 1.0
            else:
                return False
            return True
    _apply(_CRP, "CRP",
           lambda n: f"constant {n.value!r} at line {getattr(n, 'lineno', '?')}")

    # RVR: return-value replacement (return EXPR -> return None), only where the
    # original returns a value (so it is a real behaviour change).
    class _RVR:
        @staticmethod
        def collect(fn):
            return [n for n in ast.walk(fn)
                    if isinstance(n, ast.Return) and n.value is not None
                    and not (isinstance(n.value, ast.Constant) and n.value.value is None)]
        @staticmethod
        def mutate(node):
            node.value = ast.Constant(value=None)
            return True
    _apply(_RVR, "RVR",
           lambda n: f"return value at line {getattr(n, 'lineno', '?')}")

    return mutants
