"""Tests for the experiment-results browsing endpoints."""

import json

import pytest
from fastapi.testclient import TestClient

from qallm.api.main import app

client = TestClient(app)


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    run = tmp_path / "heval_demo"
    run.mkdir()
    (run / "manifest.json").write_text(json.dumps({
        "models": ["openai:gpt-4o-mini"], "strategies": ["rl"],
        "rounds": 5, "sample_size": 10, "started_at": "2026-05-30T10:00:00"}))
    (run / "aggregates.json").write_text(json.dumps([{
        "strategy": "rl", "model": "openai:gpt-4o-mini", "n_problems": 10,
        "n_bug_detected": 8, "n_repair_successful": 6, "n_errored": 0,
        "mean_rounds": 3.0, "mean_cost_usd": 0.1, "mean_elapsed_seconds": 30.0,
        "bug_detection_rate": 0.8, "repair_success_rate": 0.6}]))
    (run / "results.jsonl").write_text(
        json.dumps({"task_id": "Python/0", "strategy": "rl",
                    "model": "openai:gpt-4o-mini", "bug_detected": True,
                    "repair_successful": True, "rounds_run": 3,
                    "final_coverage": 90.0, "cost_usd": 0.1,
                    "elapsed_seconds": 30.0, "error": None}) + "\n")
    (run / "report.md").write_text("# Report\n\nbody\n")
    # Point both the config and the already-imported router module at tmp.
    monkeypatch.setattr("qallm.config.settings.QALLM_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr("qallm.api.routers.experiments.settings.QALLM_RUNS_DIR",
                        str(tmp_path))
    return tmp_path


def test_list_runs(runs_dir):
    r = client.get("/api/experiments")
    assert r.status_code == 200
    runs = r.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["id"] == "heval_demo"
    assert runs[0]["n_results"] == 1
    assert runs[0]["has_report"] is True


def test_list_empty_when_no_dir(monkeypatch):
    monkeypatch.setattr("qallm.api.routers.experiments.settings.QALLM_RUNS_DIR",
                        "/nonexistent/path/xyz")
    r = client.get("/api/experiments")
    assert r.status_code == 200
    assert r.json()["runs"] == []


def test_get_one_run(runs_dir):
    r = client.get("/api/experiments/heval_demo")
    assert r.status_code == 200
    body = r.json()
    assert body["manifest"]["rounds"] == 5
    assert body["aggregates"][0]["bug_detection_rate"] == 0.8


def test_get_results(runs_dir):
    r = client.get("/api/experiments/heval_demo/results")
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 1
    assert results[0]["task_id"] == "Python/0"


def test_get_report(runs_dir):
    r = client.get("/api/experiments/heval_demo/report")
    assert r.status_code == 200
    assert "# Report" in r.json()["markdown"]


def test_unknown_run_404(runs_dir):
    assert client.get("/api/experiments/nope").status_code == 404


def test_path_traversal_blocked(runs_dir):
    # Encoded traversal must not escape the runs dir.
    assert client.get("/api/experiments/..%2f..%2fetc").status_code in (400, 404)
