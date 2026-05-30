"""Tests for the session-library endpoints."""

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from qallm.api.main import app
from qallm.api.routers.sessions_library import _session_path_or_404

client = TestClient(app)


@pytest.fixture
def sessions_dir(tmp_path, monkeypatch):
    s = tmp_path / "20260530_120000"
    s.mkdir()
    (s / "summary.json").write_text(json.dumps({
        "source": "buggy.py", "strategy": "feedback", "model": "gpt-4o-mini",
        "lifecycle_stage": "implementation", "oracle": "crash",
        "rounds_per_function": 5, "units_analyzed": 1, "functions_verified": 3,
        "rounds_accepted_total": 4, "rounds_abandoned_total": 2,
        "halt_reason": "MAX_ROUNDS",
        "profile": {"profile_id": "implementation_default"},
        "cost": {"total_cost_usd": 0.34}}))
    (s / "report.md").write_text("# QALLM session report\n\nbody\n")
    monkeypatch.setattr("qallm.config.settings.QALLM_SESSIONS_DIR", str(tmp_path))
    monkeypatch.setattr(
        "qallm.api.routers.sessions_library.settings.QALLM_SESSIONS_DIR",
        str(tmp_path))
    return tmp_path


def test_list_sessions(sessions_dir):
    r = client.get("/api/library")
    assert r.status_code == 200
    sessions = r.json()["sessions"]
    assert len(sessions) == 1
    card = sessions[0]
    assert card["id"] == "20260530_120000"
    assert card["strategy"] == "feedback"
    assert card["profile_id"] == "implementation_default"
    assert card["total_cost_usd"] == 0.34
    assert card["has_report"] is True


def test_list_empty_when_no_dir(monkeypatch):
    monkeypatch.setattr(
        "qallm.api.routers.sessions_library.settings.QALLM_SESSIONS_DIR",
        "/nonexistent/xyz")
    r = client.get("/api/library")
    assert r.status_code == 200
    assert r.json()["sessions"] == []


def test_get_one_session(sessions_dir):
    r = client.get("/api/library/20260530_120000")
    assert r.status_code == 200
    summary = r.json()["summary"]
    assert summary["strategy"] == "feedback"
    assert summary["functions_verified"] == 3


def test_get_report(sessions_dir):
    r = client.get("/api/library/20260530_120000/report")
    assert r.status_code == 200
    assert "QALLM session report" in r.json()["markdown"]


def test_unknown_session_404(sessions_dir):
    assert client.get("/api/library/nope").status_code == 404


def test_path_traversal_guard_blocks_escapes():
    # Unit-level: the guard rejects traversal and multi-segment ids.
    for bad in ["../etc", "..", ".", "", "a/b", "a\\b"]:
        with pytest.raises(HTTPException) as exc:
            _session_path_or_404(bad)
        assert exc.value.status_code == 400
