"""Test the gap-confidence endpoint contract.

The scoring internals are covered by test_gap_confidence.py; here we verify the
endpoint wiring: unknown sessions report unavailable, and a session with no gap
findings returns a well-formed empty distribution rather than erroring.
"""

from fastapi.testclient import TestClient

from qallm.api.main import app

client = TestClient(app)


def test_gap_confidence_unknown_session(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "qallm.api.routers.results.settings.QALLM_SESSIONS_DIR", str(tmp_path))
    r = client.get("/api/session/nope/gap-confidence")
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_gap_confidence_session_without_gap(tmp_path, monkeypatch):
    # A session dir that exists but has no round artefacts: endpoint should
    # report available with an empty distribution, not crash.
    sid = "empty_sess"
    (tmp_path / sid).mkdir()
    monkeypatch.setattr(
        "qallm.api.routers.results.settings.QALLM_SESSIONS_DIR", str(tmp_path))
    r = client.get(f"/api/session/{sid}/gap-confidence")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["scored"] == 0
    assert body["distribution"] == {
        "high": 0, "medium": 0, "low": 0, "unknown": 0}
