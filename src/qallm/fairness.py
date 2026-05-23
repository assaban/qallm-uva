"""FAIRness indicators for QALLM.

Implements workflow design v3 section 9.4: four project-level indicators that
together approximate the FAIR4RS principles' core "findable and reusable"
criteria for research software. Three indicators check for required project
artefacts (licence, citation file, README); one is code-shaped (docstring
coverage).

These indicators are intentionally small and falsifiable. They are NOT a
comprehensive FAIR assessment: that requires manual evaluation by a human
familiar with the project's domain. They ARE a useful, cheap, automatable
signal that the project author has paid the basic price of admission for
sharing research software.

Pipeline
--------

.. code-block:: text

    Profile evaluation
           |
           v
    ┌──────────────────────────────────────────────────────┐
    │  qallm.evaluation.evaluate_profile(profile, source,  │
    │                                    context)          │
    └──────────────────────────────────────────────────────┘
           |
           |  resolves four evaluator IDs to functions in this module
           v
    ┌──────────────────────────────────────────────────────┐
    │  qallm.fairness.licence       (reads project_root)   │
    │  qallm.fairness.citation      (reads project_root)   │
    │  qallm.fairness.readme        (reads project_root)   │
    │  qallm.fairness.docstring_coverage  (reads source)   │
    └──────────────────────────────────────────────────────┘
           |
           v
       Each returns float | None
           |
           v
       IndicatorResult: pass / fail / skipped per threshold


Indicator semantics
-------------------

``licence``
    1.0 if a recognised licence file exists at the project root; 0.0
    otherwise. SKIPPED if no ``project_root`` in context.

``citation``
    1.0 if a CITATION.cff or CITATION.bib (or lowercase variants) exists;
    0.0 otherwise. SKIPPED if no ``project_root``.

``readme``
    1.0 if a README file exists, has at least 200 characters of body, AND
    contains all required section keywords (description, installation,
    usage). 0.0 if README exists but fails any check. SKIPPED if no
    ``project_root``.

``docstring_coverage``
    Fraction of functions/methods/classes in ``source`` that have a
    non-empty docstring. Defaults to counting only public symbols (no
    leading underscore); set ``context['include_private'] = True`` to
    count private ones too. Returns None (SKIPPED) if the source contains
    no definitions to count.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------- file-presence helpers ----------

# All candidate filenames are matched case-insensitively against the directory
# listing. Different projects use different conventions; we honour them all.

LICENCE_NAMES = (
    "LICENSE",
    "LICENCE",
    "LICENSE.txt",
    "LICENCE.txt",
    "LICENSE.md",
    "LICENCE.md",
    "COPYING",
    "COPYING.txt",
)

CITATION_NAMES = (
    "CITATION.cff",
    "CITATION.bib",
)

README_NAMES = (
    "README.md",
    "README.rst",
    "README.txt",
    "README",
)

# Required sections in a "FAIR" README. Each tuple is a set of accepted
# synonyms; matching any one counts as the section present.
README_REQUIRED_SECTIONS: tuple[tuple[str, ...], ...] = (
    ("description", "about", "overview", "introduction"),
    ("install", "installation", "setup", "getting started"),
    ("usage", "use", "example", "examples", "how to use"),
)

README_MIN_BODY_CHARS = 200


def _find_case_insensitive(root: Path, candidates: tuple[str, ...]) -> Path | None:
    """Return the first existing file under ``root`` whose name matches any
    candidate (case-insensitive). Returns ``None`` if no match exists.
    """
    try:
        entries = {p.name.lower(): p for p in root.iterdir() if p.is_file()}
    except (OSError, PermissionError):
        return None
    for name in candidates:
        match = entries.get(name.lower())
        if match is not None:
            return match
    return None


# ---------- evaluators ----------


def _fairness_licence(source: str, context: dict[str, Any]) -> float | None:
    """1.0 if any recognised licence file is present at the project root.

    Names accepted (case-insensitive): LICENSE, LICENCE, LICENSE.txt,
    LICENCE.txt, LICENSE.md, LICENCE.md, COPYING, COPYING.txt.

    SKIPPED if no ``project_root`` in context, mirroring the
    ``qallm.repro.manifest`` pattern.
    """
    root = context.get("project_root")
    if root is None:
        return None
    root_path = Path(root)
    if not root_path.exists() or not root_path.is_dir():
        return None
    return 1.0 if _find_case_insensitive(root_path, LICENCE_NAMES) else 0.0


def _fairness_citation(source: str, context: dict[str, Any]) -> float | None:
    """1.0 if CITATION.cff or CITATION.bib (case-insensitive) is present."""
    root = context.get("project_root")
    if root is None:
        return None
    root_path = Path(root)
    if not root_path.exists() or not root_path.is_dir():
        return None
    return 1.0 if _find_case_insensitive(root_path, CITATION_NAMES) else 0.0


def _fairness_readme(source: str, context: dict[str, Any]) -> float | None:
    """1.0 if a README is present, non-trivial, and has required sections.

    Three checks, all must pass:

      1. A README.* file exists at the project root.
      2. Its body is at least ``README_MIN_BODY_CHARS`` characters.
      3. It mentions each of the three required sections (matching any of
         the accepted synonyms in each group, case-insensitive).

    The synonyms are deliberately permissive so this indicator does not
    penalise different but reasonable README structures. The required
    structure ("description / install / usage") is itself a methodological
    opinion; it is documented in the thesis as a working definition of a
    minimally FAIR research-software README.
    """
    root = context.get("project_root")
    if root is None:
        return None
    root_path = Path(root)
    if not root_path.exists() or not root_path.is_dir():
        return None

    readme_path = _find_case_insensitive(root_path, README_NAMES)
    if readme_path is None:
        return 0.0

    try:
        body = readme_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0.0

    if len(body.strip()) < README_MIN_BODY_CHARS:
        return 0.0

    lower = body.lower()
    for section_synonyms in README_REQUIRED_SECTIONS:
        if not any(syn in lower for syn in section_synonyms):
            return 0.0

    return 1.0


def _fairness_docstring_coverage(
    source: str, context: dict[str, Any]
) -> float | None:
    """Fraction of definitions (functions/classes/methods) that have a docstring.

    Walks the source's AST and counts every ``FunctionDef``,
    ``AsyncFunctionDef``, and ``ClassDef`` node. Returns
    ``documented / total`` as a float in [0, 1].

    By default counts only public symbols (those whose names do not start
    with an underscore). Set ``context['include_private'] = True`` to count
    private ones as well.

    SKIPPED in two cases:
      * The source cannot be parsed (syntax error). We do not want a bad
        snippet to be counted as 0% documented; that is misleading.
      * The source contains zero countable definitions. Coverage is then
        undefined and we report SKIPPED rather than a placeholder.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    include_private = bool(context.get("include_private", False))

    total = 0
    documented = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if not include_private and node.name.startswith("_"):
            continue
        total += 1
        if ast.get_docstring(node):
            documented += 1

    if total == 0:
        return None
    return documented / total
