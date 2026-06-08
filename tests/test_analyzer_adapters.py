"""Tests for the static-analysis adapters and the analyzer registry.

These were at 0% coverage, yet they produce the findings the whole gap metric
counts. The registry is pure logic; the tool adapters are tested both for the
"tool not installed" path and, via a patched subprocess, the normal path, so a
change to how a tool is invoked or its result shaped is caught. Exercises the
real classes, not mocks of them.
"""

from pathlib import Path


from qallm.analysis.analyzer_registry import AnalyzerRegistry
from qallm.analysis.ruff_analyzer import RuffAnalyzer
from qallm.analysis.trufflehog_analyzer import TruffleHogAnalyzer
from qallm.common.model import CodeUnit


def _unit(tmp_path: Path, source: str = "x = 1\n") -> CodeUnit:
    p = tmp_path / "cell.py"
    p.write_text(source)
    return CodeUnit(source_code=source, cell_index=-1, original_path=p)


# ── registry ──

class _Fake:
    def __init__(self, name): self._n = name
    def tool_name(self): return self._n


def test_registry_lists_sorted_names():
    reg = AnalyzerRegistry([_Fake("ruff"), _Fake("bandit"), _Fake("radon")])
    assert reg.list() == ["bandit", "radon", "ruff"]


def test_registry_get_returns_the_analyzer():
    a = _Fake("ruff")
    reg = AnalyzerRegistry([a])
    assert reg.get("ruff") is a


def test_registry_pick_none_returns_all():
    reg = AnalyzerRegistry([_Fake("ruff"), _Fake("bandit")])
    assert {x.tool_name() for x in reg.pick(None)} == {"ruff", "bandit"}


def test_registry_pick_filters_and_ignores_unknown():
    reg = AnalyzerRegistry([_Fake("ruff"), _Fake("bandit")])
    picked = reg.pick(["ruff", "nonexistent"])
    assert [x.tool_name() for x in picked] == ["ruff"]


# ── ruff adapter ──

def test_ruff_reports_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr("qallm.analysis.ruff_analyzer.shutil.which", lambda _: None)
    res = RuffAnalyzer().analyze(_unit(tmp_path))
    assert res.tool == "ruff"
    assert res.exit_code == 127
    assert "not installed" in res.stderr


def test_ruff_runs_when_installed(tmp_path, monkeypatch):
    monkeypatch.setattr("qallm.analysis.ruff_analyzer.shutil.which", lambda _: "/usr/bin/ruff")

    class _Proc:
        returncode = 0
        stdout = "[]"
        stderr = ""

    monkeypatch.setattr("qallm.analysis.ruff_analyzer.subprocess.run",
                        lambda *a, **k: _Proc())
    res = RuffAnalyzer().analyze(_unit(tmp_path))
    assert res.tool == "ruff"
    assert res.exit_code == 0
    assert res.stdout == "[]"


def test_ruff_tool_name():
    assert RuffAnalyzer().tool_name() == "ruff"


# ── trufflehog adapter ──

def test_trufflehog_reports_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr("qallm.analysis.trufflehog_analyzer.shutil.which", lambda _: None)
    res = TruffleHogAnalyzer().analyze(_unit(tmp_path))
    assert res.tool == "trufflehog"
    assert res.exit_code == 127
    assert "not installed" in res.stderr


def test_trufflehog_runs_when_installed(tmp_path, monkeypatch):
    monkeypatch.setattr("qallm.analysis.trufflehog_analyzer.shutil.which",
                        lambda _: "/usr/bin/trufflehog")

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr("qallm.analysis.trufflehog_analyzer.subprocess.run",
                        lambda *a, **k: _Proc())
    res = TruffleHogAnalyzer().analyze(_unit(tmp_path, "API_KEY = 'sk-test'\n"))
    assert res.tool == "trufflehog"
    assert res.exit_code == 0


def test_trufflehog_tool_name():
    assert TruffleHogAnalyzer().tool_name() == "trufflehog"
