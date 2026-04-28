"""Extract functions from Python source files using the ast module.

This module parses Python source code and extracts function definitions
with their signatures, docstrings, and source text. It handles both
top-level functions and methods within classes.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from qallm.verification.models import FunctionInfo

logger = logging.getLogger(__name__)


def _get_annotation_str(annotation: ast.expr | None) -> str | None:
    """Convert an AST annotation node to a readable string."""
    if annotation is None:
        return None
    return ast.unparse(annotation)


def _extract_args(func: ast.FunctionDef) -> list[tuple[str, str | None]]:
    """Extract argument names and type annotations from a function def."""
    result: list[tuple[str, str | None]] = []
    for arg in func.args.args:
        if arg.arg == "self":
            continue
        annotation = _get_annotation_str(arg.annotation)
        result.append((arg.arg, annotation))
    return result


def extract_functions_from_source(source: str, filepath: str = "<string>") -> list[FunctionInfo]:
    """Parse Python source and extract all function definitions.

    Extracts top-level functions and class methods. Skips:
    - Functions whose names start with underscore (private)
    - Functions with no body beyond 'pass' or '...'
    - Nested functions (closures)

    Args:
        source: Python source code as a string.
        filepath: Path to the source file (for reporting).

    Returns:
        List of FunctionInfo objects, one per extractable function.
    """
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as exc:
        logger.warning("Cannot parse %s: %s", filepath, exc)
        return []

    source_lines = source.splitlines(keepends=True)
    functions: list[FunctionInfo] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Skip private/dunder functions (except __init__ which we might want later)
        if node.name.startswith("_"):
            continue

        # Skip trivial functions (only pass or ...)
        body = node.body
        if len(body) == 1:
            stmt = body[0]
            if isinstance(stmt, ast.Pass):
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                if stmt.value.value is ...:
                    continue

        # Extract source text
        start = node.lineno - 1
        end = node.end_lineno if node.end_lineno else start + 1
        func_source = "".join(source_lines[start:end])

        # Extract docstring
        docstring = ast.get_docstring(node)

        # Extract arguments
        args = _extract_args(node)

        functions.append(
            FunctionInfo(
                name=node.name,
                source=func_source,
                docstring=docstring,
                args=args,
                lineno=node.lineno,
                filepath=filepath,
            )
        )

    return functions


def extract_functions_from_file(filepath: Path) -> list[FunctionInfo]:
    """Extract functions from a Python file on disk."""
    source = filepath.read_text(encoding="utf-8")
    return extract_functions_from_source(source, filepath=str(filepath))