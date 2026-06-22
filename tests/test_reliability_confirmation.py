"""Tests for reliability confirmation from execution-only gap defects.

Static analysers emit no RELIABILITY findings, so the static-finding confirm
path can never confirm a reliability defect. These tests pin the reframe: a gap
defect (a correctness test that failed on the baseline) is treated as a
confirmed reliability defect, and its reproducing test drives RQ3.
"""
from __future__ import annotations

from pathlib import Path

from qallm.experiments.confirm_verify import (
    _module_name_from_findings,
    _reliability_confirmations,
)


def _gap_session(tmp: Path) -> tuple[str, list[dict]]:
    """A baseline with one gap function and its reproducing test."""
    unit = tmp / "lineage" / "round_00" / "unit_c0"
    (unit / "tests").mkdir(parents=True)
    (unit / "source.py").write_text("def f(n):\n    return n\n")
    (unit / "tests" / "test_f.py").write_text(
        "from source_unit_c0 import f\n"
        "def test_f(): assert f(1) == 2\n"
    )
    gap_rounds = [{"round": 0, "execution_only_functions": ["f"]}]
    return str(tmp), gap_rounds


def test_gap_defect_becomes_confirmed_reliability(tmp_path: Path) -> None:
    report_dir, gap_rounds = _gap_session(tmp_path)
    confs = _reliability_confirmations(report_dir, gap_rounds)
    assert len(confs) == 1
    c = confs[0]
    assert c["verdict"] == "confirmed"
    assert c["type"] == "RELIABILITY"
    assert c["function"] == "f"
    assert "from source_unit_c0 import f" in c["reproducing_test"]


def test_no_gap_functions_no_confirmations(tmp_path: Path) -> None:
    report_dir, _ = _gap_session(tmp_path)
    assert _reliability_confirmations(report_dir, [{"round": 0, "execution_only_functions": []}]) == []


def test_module_name_derived_from_reproducing_test() -> None:
    findings = [{"reproducing_test": "from source_widget_c0 import g\ndef test_g(): pass"}]
    assert _module_name_from_findings(findings) == "source_widget_c0"


def test_module_name_none_without_import() -> None:
    assert _module_name_from_findings([{"reproducing_test": "def test_x(): pass"}]) is None
