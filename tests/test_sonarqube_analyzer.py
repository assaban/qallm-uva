"""Tests for the optional SonarQube analyzer and normalizer.

The live scan path needs a running SonarQube server, so these tests cover
the parts that do not: the no-op-when-unconfigured behaviour, conditional
registration, and the normalizer mapping Sonar's issue JSON to Findings.
"""

import json

from qallm.analysis.analysis_manager import AnalysisManager
from qallm.analysis.analysis_model import RawToolResult
from qallm.analysis.normalization.sonarqube_normalizer import SonarQubeNormalizer
from qallm.analysis.sonarqube_analyzer import SonarQubeAnalyzer
from qallm.common.model import CodeUnit


def _unit(src="def f():\n    return 1\n"):
    from pathlib import Path
    return CodeUnit(source_code=src, original_path=Path("cell.py"), cell_index=0)


def test_unconfigured_is_noop(monkeypatch):
    monkeypatch.setattr("qallm.config.settings.SONARQUBE_URL", None)
    monkeypatch.setattr("qallm.config.settings.SONARQUBE_TOKEN", None)
    assert SonarQubeAnalyzer.is_configured() is False
    result = SonarQubeAnalyzer().analyze(_unit())
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["issues"] == []


def test_not_registered_when_unconfigured(monkeypatch):
    monkeypatch.setattr("qallm.config.settings.SONARQUBE_URL", None)
    monkeypatch.setattr("qallm.config.settings.SONARQUBE_TOKEN", None)
    names = [a.tool_name() for a in AnalysisManager().available_analyzers]
    assert "sonarqube" not in names
    assert "bandit" in names and "Radon" in names


def test_registered_when_configured(monkeypatch):
    monkeypatch.setattr("qallm.config.settings.SONARQUBE_URL", "http://localhost:9000")
    monkeypatch.setattr("qallm.config.settings.SONARQUBE_TOKEN", "tok")
    assert SonarQubeAnalyzer.is_configured() is True
    names = [a.tool_name() for a in AnalysisManager().available_analyzers]
    assert "sonarqube" in names


def test_normalizer_maps_issue_types_and_severities():
    payload = {
        "issues": [
            {"type": "BUG", "severity": "BLOCKER", "component": "proj:cell.py",
             "line": 3, "message": "null deref", "rule": "python:S1234"},
            {"type": "VULNERABILITY", "severity": "MAJOR", "component": "proj:cell.py",
             "line": 7, "message": "sql injection", "rule": "python:S5678"},
            {"type": "CODE_SMELL", "severity": "MINOR", "component": "proj:cell.py",
             "line": 9, "message": "rename me", "rule": "python:S9999"},
        ]
    }
    result = RawToolResult(tool="sonarqube", exit_code=0,
                           stdout=json.dumps(payload), stderr="")
    findings = SonarQubeNormalizer().normalize(result)
    assert len(findings) == 3
    bug = findings[0]
    assert bug.type == "RELIABILITY" and bug.severity == "CRITICAL"
    assert bug.file == "cell.py" and bug.line == 3
    assert findings[1].type == "SECURITY" and findings[1].severity == "HIGH"
    assert findings[2].type == "MAINTAINABILITY" and findings[2].severity == "MEDIUM"


def test_normalizer_empty_and_malformed():
    assert SonarQubeNormalizer().normalize(
        RawToolResult("sonarqube", 0, "", "")) == []
    assert SonarQubeNormalizer().normalize(
        RawToolResult("sonarqube", 0, "not json", "")) == []


def test_sonar_rating_evaluators_skip_or_read():
    from qallm.evaluation import (
        _sonar_maintainability_rating,
        _sonar_reliability_rating,
        _sonar_security_rating,
        resolve,
    )
    # Registered.
    for eid in ("sonar.reliability_rating", "sonar.security_rating",
                "sonar.maintainability_rating"):
        assert resolve(eid) is not None
    # Skip when no measures in context.
    assert _sonar_reliability_rating("x", {}) is None
    # Read when present (sqale_rating backs maintainability).
    ctx = {"sonar_measures": {"reliability_rating": "1.0",
                              "security_rating": "3.0", "sqale_rating": "2.0"}}
    assert _sonar_reliability_rating("x", ctx) == 1.0
    assert _sonar_security_rating("x", ctx) == 3.0
    assert _sonar_maintainability_rating("x", ctx) == 2.0


def test_orchestrator_threads_sonar_measures_into_context(monkeypatch):
    """When configured, _sonar_measures_for returns measures the profile sees."""
    import json as _json

    from qallm.analysis.analysis_model import RawToolResult
    from qallm.orchestrator import QALLMOrchestrator

    orch = QALLMOrchestrator(rounds=1)

    # Unconfigured -> no measures, profile falls back.
    monkeypatch.setattr("qallm.config.settings.SONARQUBE_URL", None)
    monkeypatch.setattr("qallm.config.settings.SONARQUBE_TOKEN", None)
    assert orch._sonar_measures_for(_unit()) is None

    # Configured + analyzer returns measures -> they come through.
    monkeypatch.setattr("qallm.config.settings.SONARQUBE_URL", "http://localhost:9000")
    monkeypatch.setattr("qallm.config.settings.SONARQUBE_TOKEN", "tok")

    def _fake_analyze(self, unit):
        return RawToolResult(
            tool="sonarqube", exit_code=0,
            stdout=_json.dumps({"issues": [], "measures": {
                "reliability_rating": "1.0", "security_rating": "2.0",
                "sqale_rating": "1.0"}}),
            stderr="")

    monkeypatch.setattr(
        "qallm.analysis.sonarqube_analyzer.SonarQubeAnalyzer.analyze",
        _fake_analyze)
    measures = orch._sonar_measures_for(_unit())
    assert measures == {"reliability_rating": "1.0",
                        "security_rating": "2.0", "sqale_rating": "1.0"}
