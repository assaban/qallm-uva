"""Tests for qallm.fairness.

Coverage:

  * `_fairness_licence`: presence detection, case-insensitivity, every
    accepted filename variant.
  * `_fairness_citation`: presence detection for .cff and .bib.
  * `_fairness_readme`: presence, minimum length, required sections,
    synonym matching, failure modes.
  * `_fairness_docstring_coverage`: AST parsing, public vs private,
    edge cases (empty source, syntax error, zero definitions).
  * Integration via the evaluator registry: indicators resolvable by id.

These tests are pure-Python; no LLM, no subprocess. Uses pytest's tmp_path
fixture to materialise fake project trees.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qallm.evaluation import resolve
from qallm.fairness import (
    LICENCE_NAMES,
    README_MIN_BODY_CHARS,
    _fairness_citation,
    _fairness_docstring_coverage,
    _fairness_licence,
    _fairness_readme,
)


# ---------- helpers ----------


def _readme_body(*sections: str) -> str:
    """Build a README body containing the listed section headings.

    Always includes enough filler text to exceed the minimum length.
    """
    body = "# Project\n\n" + ("Some descriptive prose. " * 20) + "\n\n"
    for s in sections:
        body += f"## {s}\n\nContent for {s}.\n\n"
    return body


# ---------- licence ----------


class TestLicenceIndicator:
    def test_skipped_when_no_project_root(self):
        assert _fairness_licence("", {}) is None

    def test_skipped_when_project_root_does_not_exist(self):
        assert _fairness_licence("", {"project_root": "/no/such/path"}) is None

    def test_zero_when_root_has_no_licence(self, tmp_path: Path):
        # Empty directory; no licence files of any kind.
        assert _fairness_licence("", {"project_root": str(tmp_path)}) == 0.0

    def test_one_when_root_has_LICENSE(self, tmp_path: Path):
        (tmp_path / "LICENSE").write_text("MIT")
        assert _fairness_licence("", {"project_root": str(tmp_path)}) == 1.0

    def test_one_when_root_has_lowercase_license(self, tmp_path: Path):
        (tmp_path / "license").write_text("Apache-2.0")
        assert _fairness_licence("", {"project_root": str(tmp_path)}) == 1.0

    def test_one_when_root_has_LICENCE_british_spelling(self, tmp_path: Path):
        (tmp_path / "LICENCE").write_text("MIT")
        assert _fairness_licence("", {"project_root": str(tmp_path)}) == 1.0

    def test_one_when_root_has_COPYING(self, tmp_path: Path):
        (tmp_path / "COPYING").write_text("GPL-3.0")
        assert _fairness_licence("", {"project_root": str(tmp_path)}) == 1.0

    def test_one_when_root_has_LICENSE_md_with_extension(self, tmp_path: Path):
        (tmp_path / "LICENSE.md").write_text("Permission is hereby granted...")
        assert _fairness_licence("", {"project_root": str(tmp_path)}) == 1.0

    def test_directory_named_LICENSE_does_not_count(self, tmp_path: Path):
        # A directory with that name doesn't satisfy the indicator.
        (tmp_path / "LICENSE").mkdir()
        assert _fairness_licence("", {"project_root": str(tmp_path)}) == 0.0

    def test_all_accepted_names_each_pass(self, tmp_path: Path):
        # Exercise every name in the accepted list.
        for i, name in enumerate(LICENCE_NAMES):
            sub = tmp_path / f"proj_{i}"
            sub.mkdir()
            (sub / name).write_text("text")
            assert _fairness_licence("", {"project_root": str(sub)}) == 1.0


# ---------- citation ----------


class TestCitationIndicator:
    def test_skipped_when_no_project_root(self):
        assert _fairness_citation("", {}) is None

    def test_zero_when_no_citation_file(self, tmp_path: Path):
        assert _fairness_citation("", {"project_root": str(tmp_path)}) == 0.0

    def test_one_when_CITATION_cff_present(self, tmp_path: Path):
        (tmp_path / "CITATION.cff").write_text(
            "cff-version: 1.2.0\ntitle: Example\n"
        )
        assert _fairness_citation("", {"project_root": str(tmp_path)}) == 1.0

    def test_one_when_CITATION_bib_present(self, tmp_path: Path):
        (tmp_path / "CITATION.bib").write_text("@misc{ex, title={Example}}")
        assert _fairness_citation("", {"project_root": str(tmp_path)}) == 1.0

    def test_one_when_lowercase_citation_cff(self, tmp_path: Path):
        (tmp_path / "citation.cff").write_text("cff-version: 1.2.0")
        assert _fairness_citation("", {"project_root": str(tmp_path)}) == 1.0


# ---------- readme ----------


class TestReadmeIndicator:
    def test_skipped_when_no_project_root(self):
        assert _fairness_readme("", {}) is None

    def test_zero_when_no_readme(self, tmp_path: Path):
        assert _fairness_readme("", {"project_root": str(tmp_path)}) == 0.0

    def test_zero_when_readme_too_short(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("Tiny.")
        assert _fairness_readme("", {"project_root": str(tmp_path)}) == 0.0

    def test_zero_when_missing_required_section(self, tmp_path: Path):
        # Has description and usage but not install. Long enough.
        body = _readme_body("Description", "Usage")  # no install
        (tmp_path / "README.md").write_text(body)
        assert _fairness_readme("", {"project_root": str(tmp_path)}) == 0.0

    def test_one_when_all_required_sections_present(self, tmp_path: Path):
        body = _readme_body("Description", "Installation", "Usage")
        (tmp_path / "README.md").write_text(body)
        assert _fairness_readme("", {"project_root": str(tmp_path)}) == 1.0

    def test_synonyms_accepted(self, tmp_path: Path):
        # "About" stands in for description; "Setup" for installation;
        # "Example" for usage.
        body = _readme_body("About", "Setup", "Example")
        (tmp_path / "README.md").write_text(body)
        assert _fairness_readme("", {"project_root": str(tmp_path)}) == 1.0

    def test_case_insensitive_section_matching(self, tmp_path: Path):
        body = (
            "# Project\n\n" + ("Long enough body text. " * 20) + "\n\n"
            "## DESCRIPTION\n\ntext\n\n"
            "## installation\n\ntext\n\n"
            "## Usage\n\ntext\n\n"
        )
        (tmp_path / "README.md").write_text(body)
        assert _fairness_readme("", {"project_root": str(tmp_path)}) == 1.0

    def test_readme_without_extension_accepted(self, tmp_path: Path):
        body = _readme_body("Description", "Installation", "Usage")
        (tmp_path / "README").write_text(body)
        assert _fairness_readme("", {"project_root": str(tmp_path)}) == 1.0

    def test_min_body_chars_threshold_is_a_constant(self):
        # Surface this as an explicit assertion so the methodology
        # chapter has a stable reference: 200 chars minimum.
        assert README_MIN_BODY_CHARS == 200


# ---------- docstring coverage ----------


class TestDocstringCoverage:
    def test_skipped_on_empty_source(self):
        assert _fairness_docstring_coverage("", {}) is None

    def test_skipped_on_source_without_definitions(self):
        src = "x = 1\ny = 2\nprint(x + y)\n"
        assert _fairness_docstring_coverage(src, {}) is None

    def test_skipped_on_syntax_error(self):
        # An evaluator must not penalise broken syntax as 0% documented.
        src = "def f(:\n    pass\n"
        assert _fairness_docstring_coverage(src, {}) is None

    def test_all_documented_returns_one(self):
        src = (
            'def a():\n    """A."""\n    pass\n\n'
            'def b():\n    """B."""\n    pass\n'
        )
        assert _fairness_docstring_coverage(src, {}) == 1.0

    def test_none_documented_returns_zero(self):
        src = "def a():\n    pass\n\ndef b():\n    pass\n"
        assert _fairness_docstring_coverage(src, {}) == 0.0

    def test_half_documented_returns_half(self):
        src = (
            'def a():\n    """A."""\n    pass\n\n'
            "def b():\n    pass\n"
        )
        assert _fairness_docstring_coverage(src, {}) == 0.5

    def test_default_excludes_private_functions(self):
        # _private has no docstring; public has one. Default mode counts
        # only public => 1/1 = 1.0.
        src = (
            'def public():\n    """Yes."""\n    pass\n\n'
            "def _private():\n    pass\n"
        )
        assert _fairness_docstring_coverage(src, {}) == 1.0

    def test_include_private_changes_count(self):
        src = (
            'def public():\n    """Yes."""\n    pass\n\n'
            "def _private():\n    pass\n"
        )
        # Now 1/2 = 0.5.
        assert (
            _fairness_docstring_coverage(src, {"include_private": True})
            == 0.5
        )

    def test_classes_and_methods_are_counted(self):
        src = (
            'class Foo:\n    """A class."""\n'
            '    def bar(self):\n        """A method."""\n        return 1\n\n'
            "    def baz(self):\n        return 2\n"
        )
        # 2/3 documented (Foo and bar yes, baz no).
        assert _fairness_docstring_coverage(src, {}) == pytest.approx(2 / 3)

    def test_async_functions_are_counted(self):
        src = (
            'async def fetch():\n    """Fetches."""\n    pass\n\n'
            "async def parse():\n    pass\n"
        )
        assert _fairness_docstring_coverage(src, {}) == 0.5


# ---------- registry integration ----------


class TestEvaluatorRegistration:
    """Confirm the four indicators are reachable through the registry."""

    @pytest.mark.parametrize(
        "evaluator_id",
        [
            "qallm.fairness.licence",
            "qallm.fairness.license",  # American spelling alias
            "qallm.fairness.citation",
            "qallm.fairness.readme",
            "qallm.fairness.docstring_coverage",
        ],
    )
    def test_evaluator_resolvable(self, evaluator_id: str):
        fn = resolve(evaluator_id)
        assert callable(fn)

    def test_licence_aliases_point_at_same_function(self):
        british = resolve("qallm.fairness.licence")
        american = resolve("qallm.fairness.license")
        assert british is american
