"""Tests for attaching mutation-based confidence to gap findings."""

from pathlib import Path
from qallm.experiments.gap_confidence import score_gap_confidence_from_dir


def _make_report(tmp_path: Path, source: str, tests: dict[str, str],
                 round_name: str = "round_00") -> Path:
    unit = tmp_path / "lineage" / round_name / "unit.py__0"
    (unit / "tests").mkdir(parents=True)
    (unit / "source.py").write_text(source)
    for fn, code in tests.items():
        (unit / "tests" / f"test_{fn}.py").write_text(code)
    return tmp_path


SRC = "def inc(start, end):\n    return end - start + 1\n"
STRONG = ("from source_module import inc\n"
          "def test_a():\n    assert inc(0, 10) == 11\n"
          "def test_b():\n    assert inc(5, 5) == 1\n")
WEAK = ("from source_module import inc\n"
        "def test_a():\n    assert isinstance(inc(0, 10), int)\n")


def test_strong_gap_function_scores_high(tmp_path):
    rd = _make_report(tmp_path, SRC, {"inc": STRONG})
    res = score_gap_confidence_from_dir(str(rd), ["inc"])
    assert res["scored"] == 1
    assert res["per_function"]["inc"]["confidence"] == "high"
    assert res["distribution"]["high"] == 1


def test_weak_gap_function_scores_low(tmp_path):
    rd = _make_report(tmp_path, SRC, {"inc": WEAK})
    res = score_gap_confidence_from_dir(str(rd), ["inc"])
    assert res["per_function"]["inc"]["confidence"] in ("low", "medium")


def test_restricts_to_requested_functions(tmp_path):
    rd = _make_report(tmp_path, SRC, {"inc": STRONG})
    # ask for a function that has no suite -> nothing scored
    res = score_gap_confidence_from_dir(str(rd), ["other"])
    assert res["scored"] == 0


def test_tolerates_round_0_naming(tmp_path):
    rd = _make_report(tmp_path, SRC, {"inc": STRONG}, round_name="round_0")
    res = score_gap_confidence_from_dir(str(rd), ["inc"])
    assert res["scored"] == 1


def test_missing_report_dir_is_safe(tmp_path):
    res = score_gap_confidence_from_dir(str(tmp_path / "nope"), ["inc"])
    assert res["scored"] == 0
    assert res["per_function"] == {}
