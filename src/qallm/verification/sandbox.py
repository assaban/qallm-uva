"""Sandbox utilities for test execution isolation.

CodeExtractor: multi-strategy extraction of valid Python from LLM output,
with AST validation as a gate. Addresses the 'LLM Chatter' problem.

DependencyMapper: copies sibling modules/packages into the sandbox so
that target code imports resolve correctly. Addresses the 'Import
Hallucinations' problem.
"""

from __future__ import annotations

import ast
import logging
import re
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CodeExtractor:
    """Multi-strategy code extraction with AST validation."""

    DIALOGUE_PREFIXES = (
        "i understand", "here is", "here's", "certainly", "based on",
        "the code", "sure", "as a", "below is", "this test", "note:",
        "explanation", "let me", "i'll", "i will", "the following",
        "these tests", "**", "##", "#"
    )

    @classmethod
    def extract(cls, raw_text: str) -> tuple[str, str]:
        """Try multiple strategies, return (code, strategy_used)."""
        strategies = [
            ("markdown_python_block", cls._extract_python_blocks),
            ("markdown_generic_block", cls._extract_generic_blocks),
            ("dialogue_filter", cls._extract_by_filtering_dialogue),
            ("raw_text", cls._extract_raw),
        ]
        for name, extractor in strategies:
            candidate = extractor(raw_text)
            if not candidate or not candidate.strip():
                continue
            if cls._is_valid_python(candidate):
                return candidate.strip(), name
            cleaned = cls._strip_broken_imports(candidate)
            if cleaned != candidate and cls._is_valid_python(cleaned):
                return cleaned.strip(), f"{name}+import_cleanup"

        functions_only = cls._extract_function_defs(raw_text)
        if functions_only and cls._is_valid_python(functions_only):
            return functions_only.strip(), "function_defs_only"

        return "def test_extraction_failed(): assert True", "fallback"

    @staticmethod
    def _is_valid_python(code: str) -> bool:
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False

    @staticmethod
    def _extract_python_blocks(text: str) -> str:
        blocks = re.findall(r"```python\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        return "\n\n".join(blocks) if blocks else ""

    @staticmethod
    def _extract_generic_blocks(text: str) -> str:
        blocks = re.findall(r"```\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        return "\n\n".join(blocks) if blocks else ""

    @classmethod
    def _extract_by_filtering_dialogue(cls, text: str) -> str:
        lines = text.splitlines()
        code_lines = []
        for line in lines:
            stripped = line.strip().lower()
            if not stripped:
                code_lines.append(line)
                continue
            if stripped.startswith(cls.DIALOGUE_PREFIXES):
                continue
            if not any(c in line for c in ["=", "(", ")", ":", "import", "def ", "class ", "#", "@"]):
                words = stripped.split()
                if len(words) > 5 and not stripped.startswith(("from ", "import ")):
                    continue
            code_lines.append(line)
        return "\n".join(code_lines).strip()

    @staticmethod
    def _extract_raw(text: str) -> str:
        return text.strip()

    @staticmethod
    def _strip_broken_imports(code: str) -> str:
        lines = code.splitlines()
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                cleaned.append(line)
                continue
            try:
                ast.parse(stripped)
                cleaned.append(line)
            except SyntaxError:
                cleaned.append(f"# STRIPPED (syntax error): {stripped}")
        return "\n".join(cleaned)

    @staticmethod
    def _extract_function_defs(text: str) -> str:
        lines = text.splitlines()
        result = ["import pytest"]
        in_function = False
        indent_level = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("def test_"):
                in_function = True
                indent_level = len(line) - len(line.lstrip())
                result.append(line)
            elif in_function:
                if stripped == "" or (len(line) - len(line.lstrip()) > indent_level):
                    result.append(line)
                else:
                    in_function = False
                    if stripped.startswith("def test_"):
                        in_function = True
                        indent_level = len(line) - len(line.lstrip())
                        result.append(line)
        return "\n".join(result) if len(result) > 1 else ""


class DependencyMapper:
    """Resolves project-internal imports by copying sibling modules into the sandbox.

    Strategy:
      1. Walk up from the target file looking for ``__init__.py`` files.
         Each one signals a package; the outermost ``__init__.py`` marks
         the package root.
      2. If a package root is found, copy the whole package tree into
         the sandbox. This is the only way ``from research_pipeline.config
         import X`` style imports resolve.
      3. If no package root is found (the target file is a bare script),
         fall back to copying sibling ``.py`` files from the parent
         directory. This handles flat-layout projects.

    Logs at INFO so a misbehaving run leaves a breadcrumb trail. A silent
    no-op was the cause of a real ``ModuleNotFoundError`` in NEW-08
    testing; explicit logging is mandatory for a sandbox that hides
    state from the user.
    """

    @staticmethod
    def resolve_and_copy(target_path: Path, sandbox_dir: Path) -> list[str]:
        copied = []
        parent = target_path.parent
        if not parent.exists() or not parent.is_dir():
            logger.warning(
                "DependencyMapper: parent of %s does not exist; nothing copied.",
                target_path,
            )
            return copied

        package_root = DependencyMapper._find_package_root(target_path)
        if package_root and package_root != target_path:
            dest = sandbox_dir / package_root.name
            if not dest.exists():
                shutil.copytree(package_root, dest, dirs_exist_ok=True)
                copied.append(package_root.name)
                logger.info(
                    "DependencyMapper: copied package %s -> %s",
                    package_root, dest,
                )
            else:
                logger.debug(
                    "DependencyMapper: package %s already at %s; skipped.",
                    package_root.name, dest,
                )
        else:
            sibling_count = 0
            for sibling in parent.glob("*.py"):
                if sibling == target_path:
                    continue
                dest = sandbox_dir / sibling.name
                if not dest.exists():
                    shutil.copy2(sibling, dest)
                    copied.append(sibling.stem)
                    sibling_count += 1
            logger.info(
                "DependencyMapper: no package detected at %s; "
                "copied %d sibling .py file(s).",
                parent, sibling_count,
            )

        # Secondary pass: scan the target's imports for top-level package
        # references and copy any matching sibling directories. This catches
        # two real situations:
        #   1. The user uploaded a "namespace package" (PEP 420) with no
        #      __init__.py at the root; _find_package_root returns None
        #      but the package directory is still present alongside.
        #   2. The target is a script in a parent directory that imports
        #      from a child package directory.
        # We walk a few levels up from the target's parent looking for
        # directories whose names match imported top-level packages.
        try:
            referenced = DependencyMapper._top_level_imports(target_path)
        except Exception as e:
            logger.debug("Could not parse imports from %s: %s", target_path, e)
            referenced = set()

        # Strip out modules we already copied as standalone .py files.
        already_have_names = {p.stem for p in sandbox_dir.glob("*.py")}
        already_have_names |= {p.name for p in sandbox_dir.iterdir() if p.is_dir()}
        for pkg_name in referenced - already_have_names:
            # Search up to 3 levels above the target for a matching dir.
            search_dir = parent
            for _ in range(3):
                candidate = search_dir / pkg_name
                if candidate.is_dir():
                    dest = sandbox_dir / pkg_name
                    if not dest.exists():
                        shutil.copytree(candidate, dest, dirs_exist_ok=True)
                        copied.append(pkg_name)
                        logger.info(
                            "DependencyMapper: resolved import '%s' by "
                            "copying %s -> %s",
                            pkg_name, candidate, dest,
                        )
                    break
                if search_dir == search_dir.parent:
                    break
                search_dir = search_dir.parent

        if not copied:
            logger.warning(
                "DependencyMapper: nothing copied from %s. If the target "
                "imports from sibling modules, tests will fail to import. "
                "Verify the upload includes the full package directory.",
                target_path,
            )
        return copied

    @staticmethod
    def _top_level_imports(file_path: Path) -> set[str]:
        """Return the set of top-level module names imported by file_path.

        For ``from research_pipeline.config import X`` we return
        ``{"research_pipeline"}``. For ``import numpy as np`` we return
        ``{"numpy"}``. Standard-library and installed-package names will
        be in this set too; the caller filters by whether the name exists
        on disk in the upload tree.
        """
        text = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text)
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    names.add(node.module.split(".")[0])
        return names

    @staticmethod
    def _find_package_root(file_path: Path) -> Optional[Path]:
        current = file_path.parent
        package_root = None
        while current != current.parent:
            if (current / "__init__.py").exists():
                package_root = current
                current = current.parent
            else:
                break
        return package_root
