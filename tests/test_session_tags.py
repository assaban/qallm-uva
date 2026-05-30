"""Tests for session tagging: orchestrator normalisation and library filter."""

import json

import pytest
from fastapi.testclient import TestClient

from qallm.api.main import app
from qallm.orchestrator import QALLMOrchestrator

client = TestClient(app)


def test_orchestrator_normalises_tags():
    o = QALLMOrchestrator(tags=["  thesis ", "baseline", "thesis", "", "baseline"])
    # Trimmed, de-duplicated, blanks dropped, order preserved.
    assert o.tags == ["thesis", "baseline"]


def test_orchestrator_no_tags_is_empty_list():
    assert QALLMOrchestrator().tags == []
    assert QALLMOrchestrator(tags=None).tags == []


@pytest.fixture
def sessions_dir(tmp_path, monkeypatch):
    specs = {
        "s1": ["thesis", "run-1"],
        "s2": ["baseline"],
        "s3": ["thesis"],
    }
    for sid, tags in specs.items():
        d = tmp_path / sid
        d.mkdir()
        (d / "summary.json").write_text(json.dumps({
            "source": f"{sid}.py", "tags": tags, "strategy": "feedback",
            "cost": {}}))
    monkeypatch.setattr("qallm.config.settings.QALLM_SESSIONS_DIR", str(tmp_path))
    monkeypatch.setattr(
        "qallm.api.routers.sessions_library.settings.QALLM_SESSIONS_DIR",
        str(tmp_path))
    return tmp_path


def test_library_lists_tags_and_all_tags(sessions_dir):
    body = client.get("/api/library").json()
    assert len(body["sessions"]) == 3
    assert body["all_tags"] == ["baseline", "run-1", "thesis"]
    by_id = {s["id"]: s for s in body["sessions"]}
    assert by_id["s1"]["tags"] == ["thesis", "run-1"]


def test_library_filters_by_tag(sessions_dir):
    body = client.get("/api/library?tag=thesis").json()
    ids = {s["id"] for s in body["sessions"]}
    assert ids == {"s1", "s3"}
    # all_tags still reflects the full corpus, not the filtered view.
    assert body["all_tags"] == ["baseline", "run-1", "thesis"]


def test_library_filter_unknown_tag_empty(sessions_dir):
    body = client.get("/api/library?tag=nope").json()
    assert body["sessions"] == []
    assert body["all_tags"] == ["baseline", "run-1", "thesis"]
