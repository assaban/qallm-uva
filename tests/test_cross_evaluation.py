"""Tests for the variant x final-suite cross-evaluation."""
from __future__ import annotations

from pathlib import Path

from qallm.analysis.cross_evaluation import (
    _collect_final_suites,
    _content_hash,
    _discover_variants,
    _expected_module_name,
    _function_in_source,
    cross_evaluate,
)


def _make_session(tmp: Path) -> str:
    """A minimal two-round session: a buggy baseline and a repaired variant.

    inclusive_range_count is off-by-one in round 0 (end - start) and fixed in
    round 1 (end - start + 1). The same test suite is stored in both rounds.
    """
    suite = (
        "import pytest\n"
        "from source_unit_c0 import inclusive_range_count\n"
        "def expected(s, e):\n    return e - s + 1\n"
        "def test_basic():\n    assert inclusive_range_count(0, 10) == expected(0, 10)\n"
    )
    buggy = "def inclusive_range_count(start, end):\n    return end - start\n"
    fixed = "def inclusive_range_count(start, end):\n    return end - start + 1\n"

    for bucket, rnd, src in [("lineage", 0, buggy), ("lineage", 1, fixed)]:
        unit = tmp / bucket / f"round_{rnd:02d}" / "unit_c0"
        (unit / "tests").mkdir(parents=True)
        (unit / "source.py").write_text(src)
        (unit / "tests" / "test_inclusive_range_count.py").write_text(suite)
    return str(tmp)


class TestHelpers:
    def test_content_hash_normalises_whitespace(self) -> None:
        assert _content_hash("def t():  pass") == _content_hash("def t(): pass")

    def test_expected_module_name(self) -> None:
        suite = "from source_foo_c0 import bar\ndef test_x(): pass"
        assert _expected_module_name(suite) == "source_foo_c0"

    def test_function_in_source(self) -> None:
        assert _function_in_source("def foo():\n    pass", "foo")
        assert not _function_in_source("def bar():\n    pass", "foo")


class TestDiscovery:
    def test_finds_both_variants(self, tmp_path: Path) -> None:
        report_dir = _make_session(tmp_path)
        variants = _discover_variants(report_dir)
        assert len(variants) == 2
        assert {v.round_number for v in variants} == {0, 1}

    def test_collects_one_suite_per_function(self, tmp_path: Path) -> None:
        report_dir = _make_session(tmp_path)
        suites = _collect_final_suites(_discover_variants(report_dir))
        assert set(suites) == {"inclusive_range_count"}


class TestMatrix:
    def test_baseline_fails_repaired_passes_under_same_suite(self, tmp_path: Path) -> None:
        report_dir = _make_session(tmp_path)
        matrix = cross_evaluate(report_dir)
        by_round = {c.round_number: c for c in matrix.cells}
        # Same final suite: the off-by-one baseline fails, the repair passes.
        assert by_round[0].failed >= 1
        assert by_round[0].outcome == "fail"
        assert by_round[1].failed == 0
        assert by_round[1].passed >= 1
        assert by_round[1].outcome == "pass"
