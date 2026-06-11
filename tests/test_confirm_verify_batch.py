"""Tests for the batch confirm/verify-from-disk helper."""

import json
from pathlib import Path

from qallm.experiments.confirm_verify import (
    _baseline_units,
    _final_sources,
    confirm_and_verify_from_dir,
)


def _make_session(tmp_path: Path):
    """A report dir with a baseline (round_00) and a repaired (round_01).

    Uses the real zero-padded naming the reporter writes (round_{n:02d}); an
    earlier version of this fixture used round_0/round_1, which masked a bug
    where confirm/verify only looked for round_0 and so found no baseline on
    real runs (0 confirmed / 0 refuted).
    """
    rd = tmp_path / "session_1"
    base = rd / "lineage" / "round_00" / "unit"
    base.mkdir(parents=True)
    (base / "source.py").write_text("def f(x):\n    return x - 1\n")
    (base / "static.json").write_text(json.dumps([
        {"tool": "sonar", "type": "RELIABILITY", "severity": "HIGH",
         "line": 2, "message": "off-by-one", "rule_id": "S1"},
    ]))
    repaired = rd / "lineage" / "round_01" / "unit"
    repaired.mkdir(parents=True)
    (repaired / "source.py").write_text("def f(x):\n    return x + 1\n")
    (repaired / "static.json").write_text(json.dumps([]))
    return rd


def test_baseline_units_reads_round_00(tmp_path):
    rd = _make_session(tmp_path)
    units = _baseline_units(str(rd))
    assert "unit" in units
    assert "x - 1" in units["unit"]["source"]
    assert len(units["unit"]["findings"]) == 1


def test_final_sources_takes_latest_round(tmp_path):
    rd = _make_session(tmp_path)
    finals = _final_sources(str(rd))
    # round_01 is later than round_00, so the repaired source wins.
    assert "x + 1" in finals["unit"]


def test_empty_report_dir_returns_none_summaries(tmp_path):
    rd = tmp_path / "empty"
    rd.mkdir()
    out = confirm_and_verify_from_dir(str(rd), testgen_llm=None)
    assert out["confirm_summary"] is None
    assert out["verify_summary"] is None


class _FakeLLM:
    """Returns a reproducing test that fails on the buggy code (x - 1) and
    passes on the repaired code (x + 1), so the finding confirms and the fix
    verifies."""
    def chat(self, system, prompt, tracker=None):
        class R:
            content = (
                "```python\n"
                "def test_f_off_by_one():\n"
                "    assert f(3) == 4\n"
                "```\n"
            )
            error = None
            input_tokens = 0
            output_tokens = 0
        return R()


def test_confirm_and_verify_end_to_end(tmp_path):
    rd = _make_session(tmp_path)
    out = confirm_and_verify_from_dir(str(rd), testgen_llm=_FakeLLM())
    cs = out["confirm_summary"]
    assert cs is not None
    # The reliability finding should confirm (test fails on x - 1).
    assert cs["confirmed"] >= 1
    vs = out["verify_summary"]
    assert vs is not None
    # And the fix should verify (same test passes on x + 1).
    assert vs["verified_fixed"] >= 1


def test_baseline_tolerates_legacy_round_0_naming(tmp_path):
    """Back-compat: a report dir written with the old round_0 name still
    resolves, so older runs remain analysable."""
    rd = tmp_path / "legacy"
    base = rd / "lineage" / "round_0" / "unit"
    base.mkdir(parents=True)
    (base / "source.py").write_text("def f():\n    return 1\n")
    (base / "static.json").write_text("[]")
    units = _baseline_units(str(rd))
    assert "unit" in units


def test_baseline_empty_when_no_round_zero(tmp_path):
    rd = tmp_path / "empty"
    (rd / "lineage" / "round_03" / "unit").mkdir(parents=True)
    # only a late round exists; there is no baseline to confirm against
    assert _baseline_units(str(rd)) == {}
