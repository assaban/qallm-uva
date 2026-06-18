"""Tests for round-to-round code and test diffs."""
from __future__ import annotations

from pathlib import Path

from qallm.analysis.round_diff import available_rounds, diff_rounds


def _session(tmp: Path) -> str:
    suite0 = "def test_x():\n    assert f(1) == 1\n"
    suite1 = "def test_x():\n    assert f(1) == 2\n"
    src0 = "def f(n):\n    return n\n"
    src1 = "def f(n):\n    return n + 1\n"
    for rnd, src, suite in [(0, src0, suite0), (1, src1, suite1)]:
        unit = tmp / "lineage" / f"round_{rnd:02d}" / "unit_c0"
        (unit / "tests").mkdir(parents=True)
        (unit / "source.py").write_text(src)
        (unit / "tests" / "test_f.py").write_text(suite)
    return str(tmp)


def test_available_rounds(tmp_path: Path) -> None:
    assert available_rounds(_session(tmp_path)) == [0, 1]


def test_defaults_to_parent_round(tmp_path: Path) -> None:
    rd = diff_rounds(_session(tmp_path), to_round=1)
    assert rd.from_round == 0
    assert rd.to_round == 1


def test_code_diff_is_detected(tmp_path: Path) -> None:
    rd = diff_rounds(_session(tmp_path), to_round=1)
    code = next(f for f in rd.files if f.kind == "code")
    assert code.changed
    assert "return n + 1" in code.new_text
    assert "+    return n + 1" in code.unified


def test_test_diff_is_detected(tmp_path: Path) -> None:
    rd = diff_rounds(_session(tmp_path), to_round=1)
    test = next(f for f in rd.files if f.kind == "test")
    assert test.changed
    assert test.unified  # non-empty unified diff


def test_baseline_has_no_parent(tmp_path: Path) -> None:
    rd = diff_rounds(_session(tmp_path), to_round=0)
    assert rd.from_round is None
    code = next(f for f in rd.files if f.kind == "code")
    # Everything is new against an empty baseline.
    assert code.old_text == ""
    assert code.changed
