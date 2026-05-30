"""The analysis-tools list must reflect active analysers dynamically."""

from fastapi.testclient import TestClient

from qallm.api.main import app

client = TestClient(app)


def test_tools_list_without_sonarqube(monkeypatch):
    monkeypatch.setattr("qallm.config.settings.SONARQUBE_URL", None)
    monkeypatch.setattr("qallm.config.settings.SONARQUBE_TOKEN", None)
    tools = [t.lower() for t in client.get("/api/analysis/tools").json()["tools"]]
    assert "bandit" in tools and "radon" in tools
    assert "ruff" in tools and "trufflehog" in tools
    assert "sonarqube" not in tools


def test_tools_list_includes_sonarqube_when_configured(monkeypatch):
    monkeypatch.setattr("qallm.config.settings.SONARQUBE_URL", "http://sonarqube:9000")
    monkeypatch.setattr("qallm.config.settings.SONARQUBE_TOKEN", "tok")
    tools = [t.lower() for t in client.get("/api/analysis/tools").json()["tools"]]
    assert "sonarqube" in tools
    # Still no duplicates of the always-on tools.
    assert tools.count("ruff") == 1
    assert tools.count("trufflehog") == 1
