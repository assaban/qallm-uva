"""Tests for the experiment catalog, launch, progress, and dataset-to-pipeline."""

from dataclasses import dataclass
from unittest.mock import patch

from fastapi.testclient import TestClient

import qallm.api.routers.experiments_control as ec
from qallm.api.main import app

client = TestClient(app)


def test_catalog_lists_experiments_with_metadata():
    body = client.get("/api/experiment-catalog").json()
    ids = [e["id"] for e in body["experiments"]]
    assert "humanevalfix" in ids
    hef = next(e for e in body["experiments"] if e["id"] == "humanevalfix")
    assert hef["citation"]
    assert hef["dataset_url"].startswith("https://")
    assert hef["n_problems"] == 164


def test_launch_requires_models_and_strategies():
    r = client.post("/api/experiment-catalog/humanevalfix/run", json={})
    assert r.status_code == 400


def test_launch_unknown_experiment_404():
    r = client.post("/api/experiment-catalog/nope/run",
                    json={"models": ["m"], "strategies": ["rl"]})
    assert r.status_code == 404


def test_progress_untracked_run():
    body = client.get("/api/experiment-runs/never_launched/progress").json()
    assert body["tracked"] is False


def test_progress_registry_records_results():
    p = ec.RunProgress("rp_test", total=2)
    p.record({"task_id": "Python/0", "strategy": "rl", "model": "m",
              "bug_detected": True, "repair_successful": True, "error": None})
    p.record({"task_id": "Python/1", "strategy": "rl", "model": "m",
              "bug_detected": False, "repair_successful": False,
              "error": "boom"})
    snap = p.to_dict()
    assert snap["completed"] == 2
    assert snap["bug_detected"] == 1
    assert snap["repair_successful"] == 1
    assert snap["errored"] == 1
    assert len(snap["log"]) == 2


def test_run_work_drives_progress_to_done():
    @dataclass
    class FakeResult:
        task_id: str
        strategy: str
        model: str
        bug_detected: bool
        repair_successful: bool
        error: object

    def fake_run(config, on_problem_complete=None):
        out = []
        for i in range(3):
            r = FakeResult(f"Python/{i}", "rl", "stub", i != 1, i == 0, None)
            if on_problem_complete:
                on_problem_complete(r)
            out.append(r)
        return out

    ec._put_progress(ec.RunProgress("rw_test", total=3))
    with patch("qallm.experiments.humaneval_runner.run_experiment", fake_run), \
         patch("qallm.experiments.humaneval_runner.ExperimentConfig",
               lambda **k: type("C", (), k)):
        out = ec._run_experiment_work("rw_test", {"models": ["stub"], "strategies": ["rl"],
                                       "sample_size": 3})
    assert out["n_results"] == 3
    snap = ec._get_progress("rw_test").to_dict()
    assert snap["status"] == "done"
    assert snap["completed"] == 3
    assert snap["bug_detected"] == 2


def test_materialise_and_create_session():
    @dataclass
    class P:
        task_id: str
        src: str

        @property
        def buggy_full_source(self):
            return self.src

    problems = [P("Python/0", "def f():\n    return 1\n"),
                P("Python/1", "def g():\n    return 2\n")]
    d = ec._materialise_problems(problems)
    import os
    assert set(os.listdir(d)) == {"Python_0.py", "Python_1.py"}

    sid = ec._create_pipeline_session(
        d, {"model": "openai:gpt-4o-mini", "tags": ["heval"]}, "humanevalfix")
    from qallm.api.core import sessions
    assert sid in sessions
    assert len(sessions[sid]["units"]) == 2
    assert sessions[sid]["orchestrator"].tags == ["heval"]


def test_launch_without_datasets_returns_clear_400(monkeypatch):
    """A server missing the datasets package fails the launch cleanly,
    without creating a run id, progress entry, or empty run directory."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "datasets":
            raise ImportError("no datasets")
        return real_import(name, *a, **k)

    before = dict(ec._progress)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    r = client.post("/api/experiment-catalog/humanevalfix/run",
                    json={"models": ["m"], "strategies": ["feedback"]})
    assert r.status_code == 400
    assert "datasets" in r.json()["detail"]
    # No progress entry was created for a rejected launch.
    assert dict(ec._progress) == before
