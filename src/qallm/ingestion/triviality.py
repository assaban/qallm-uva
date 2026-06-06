"""Detect code units with nothing to analyze, so they can be skipped.

Empty and import-only files (a bare ``__init__.py`` is the canonical case)
have no functions, classes, or executable logic. Running them through static
analysis, test generation, and LLM repair rounds costs API tokens and time,
and pollutes the metric denominators with units that could never have a
finding or a verifiable defect. Skipping them at ingestion keeps the metrics
honest (a file with nothing to verify should not count as verified) and
saves resources.

"Trivial" is defined structurally from the AST, not by byte length: a unit
is trivial when it contains no function or class definitions and no
executable statements beyond the inert scaffolding that carries no logic to
verify, namely module docstrings, imports, ``pass``, ``...`` (Ellipsis), and
dunder/``__all__`` assignments of literals. Anything with a real statement
(a call, a loop, a non-trivial assignment, a conditional) is kept.

If the source does not parse, it is NOT treated as trivial: a syntax error
is a real signal the pipeline should see, not a unit to silently drop.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass
class TrivialityResult:
    is_trivial: bool
    reason: str  # human-readable, recorded for auditability


def _is_inert_statement(node: ast.stmt) -> bool:
    """True if a top-level statement carries no logic to verify."""
    # Imports: structural, nothing to execute meaningfully.
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return True
    # Bare pass / Ellipsis (...) expression.
    if isinstance(node, ast.Pass):
        return True
    if isinstance(node, ast.Expr):
        value = node.value
        # Module docstring or a bare string/constant expression (e.g. ...).
        if isinstance(value, ast.Constant):
            return True
        return False
    # __all__ = [...] or other dunder assignment to a literal: metadata only.
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [t.id for t in targets if isinstance(t, ast.Name)]
        is_dunder = bool(names) and all(
            n.startswith("__") and n.endswith("__") or n == "__all__" for n in names
        )
        value = node.value
        is_literal = value is None or isinstance(
            value, (ast.Constant, ast.List, ast.Tuple, ast.Set, ast.Dict)
        )
        if is_dunder and is_literal:
            return True
        return False
    return False


def assess_triviality(source_code: str) -> TrivialityResult:
    """Decide whether a unit has nothing worth running through the pipeline."""
    if not source_code or not source_code.strip():
        return TrivialityResult(True, "Empty file (no content).")

    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        # A syntax error is a real finding; do not skip it.
        return TrivialityResult(False, "Source does not parse; kept for analysis.")

    # Any function or class is analyzable by definition.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return TrivialityResult(False, "Contains functions or classes.")

    # No defs: trivial only if every top-level statement is inert.
    non_inert = [n for n in tree.body if not _is_inert_statement(n)]
    if not non_inert:
        return TrivialityResult(
            True, "No functions, classes, or executable statements (imports/comments only)."
        )

    return TrivialityResult(False, "Contains executable statements.")
