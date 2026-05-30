"""The improvement endpoint must work for historical sessions on disk.

When a session is opened from the session library it is not live in this
process's memory, so the improvement audit has to resolve its report
directory from QALLM_SESSIONS_DIR rather than from in-memory state. This
is what lets the library detail show the same lineage/verdict view as the
pipeline final report.
"""

import json
import os

from fastapi.testclient import TestClient

from qallm.api.main import app

client = TestClient(app)


def _write_session(base, sid):
    sdir = os.path.join(base, sid)
    lineage_r1 = os.path.join(sdir, "lineage", "round_01", "myfunc")
    os.makedirs(lineage_r1)
    json.dump({"delta": []}, open(os.path.join(lineage_r1, "improvement.json"), "w"))
    json.dump({"status": "pass"}, open(os.path.join(lineage_r1, "profile.json"), "w"))
    json.dump({"outcome": "improvement"}, open(os.path.join(lineage_r1, "judge.json"), "w"))
    json.dump([], open(os.path.join(lineage_r1, "transcript.json"), "w"))
    json.dump([], open(os.path.join(lineage_r1, "verification.json"), "w"))


def test_improvement_resolves_from_disk(tmp_path, monkeypatch):
    base = str(tmp_path)
    _write_session(base, "20260530_999999")
    monkeypatch.setattr("qallm.config.settings.QALLM_SESSIONS_DIR", base)
    monkeypatch.setattr("qallm.api.routers.results.settings.QALLM_SESSIONS_DIR", base)

    # This session id is NOT a live in-memory session, only on disk.
    r = client.get("/api/session/20260530_999999/improvement")
    assert r.status_code == 200
    body = r.json()
    # The endpoint found the on-disk artefacts and built rounds.
    assert body.get("available") is not False
    assert any(rd.get("round") == 1 for rd in body.get("rounds", []))


def test_improvement_absent_session_reports_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr("qallm.config.settings.QALLM_SESSIONS_DIR", str(tmp_path))
    monkeypatch.setattr("qallm.api.routers.results.settings.QALLM_SESSIONS_DIR", str(tmp_path))
    r = client.get("/api/session/does_not_exist/improvement")
    assert r.status_code == 200
    assert r.json()["available"] is False
