"""Tests for parallel file processing in the gap runner."""

import json
from pathlib import Path

from qallm.experiments.gap_runner import (
    run_gap_experiment,
    GapExperimentConfig,
)


# Module-level factory so ProcessPoolExecutor can pickle it. Returns a stub
# orchestrator-like object is not needed; _run_one builds the orchestrator via
# this factory, so we make it produce a deterministic fake result by raising a
# sentinel the runner records as an error row (no LLM needed).
def _fake_factory(config):
    raise RuntimeError("stub-no-llm")


def _make_dataset(tmp_path: Path, n: int) -> Path:
    ds = tmp_path / "ds"
    ds.mkdir()
    for i in range(n):
        (ds / f"f{i}.py").write_text(f"def g{i}(x):\n    return x\n")
    return ds


def test_parallel_processes_all_files(tmp_path):
    ds = _make_dataset(tmp_path, 4)
    cfg = GapExperimentConfig(
        dataset_dir=ds, output_dir=tmp_path / "out", pattern="*.py",
        rounds=1, workers=3,
    )
    run_gap_experiment(cfg, orchestrator_factory=_fake_factory)
    rows = (tmp_path / "out" / "results.jsonl").read_text().strip().splitlines()
    inputs = sorted(json.loads(r)["input"].split("/")[-1] for r in rows)
    assert inputs == ["f0.py", "f1.py", "f2.py", "f3.py"]


def test_workers_in_manifest(tmp_path):
    ds = _make_dataset(tmp_path, 1)
    cfg = GapExperimentConfig(
        dataset_dir=ds, output_dir=tmp_path / "out", pattern="*.py",
        rounds=1, workers=2,
    )
    run_gap_experiment(cfg, orchestrator_factory=_fake_factory)
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert manifest["workers"] == 2


def test_sequential_default_still_works(tmp_path):
    ds = _make_dataset(tmp_path, 2)
    cfg = GapExperimentConfig(
        dataset_dir=ds, output_dir=tmp_path / "out", pattern="*.py",
        rounds=1, workers=1,
    )
    run_gap_experiment(cfg, orchestrator_factory=_fake_factory)
    rows = (tmp_path / "out" / "results.jsonl").read_text().strip().splitlines()
    assert len(rows) == 2


def test_parallel_resume_skips_completed(tmp_path):
    ds = _make_dataset(tmp_path, 3)
    out = tmp_path / "out"
    out.mkdir()
    # Pre-seed one completed result; the runner should not reprocess it.
    (out / "results.jsonl").write_text(
        json.dumps({"input": str(ds / "f0.py"), "metrics": None}) + "\n"
    )
    cfg = GapExperimentConfig(
        dataset_dir=ds, output_dir=out, pattern="*.py", rounds=1, workers=2,
    )
    run_gap_experiment(cfg, orchestrator_factory=_fake_factory)
    rows = (out / "results.jsonl").read_text().strip().splitlines()
    inputs = [json.loads(r)["input"].split("/")[-1] for r in rows]
    # f0 appears once (the pre-seeded row), f1 and f2 added once each.
    assert inputs.count("f0.py") == 1
    assert "f1.py" in inputs and "f2.py" in inputs


def test_worker_logging_initializer_configures_file_handler(tmp_path):
    """Workers must configure their own logging (they do not inherit the main
    process config under spawn). The initializer attaches a FileHandler to the
    given run.log so a parallel run is not silent."""
    import logging
    from qallm.experiments.gap_runner import _init_worker_logging

    log_path = tmp_path / "run.log"
    root = logging.getLogger()
    # Snapshot and restore handlers so this test does not leak global state.
    saved = root.handlers[:]
    saved_flag = getattr(root, "_qallm_worker_configured", False)
    try:
        root.handlers = []
        if hasattr(root, "_qallm_worker_configured"):
            delattr(root, "_qallm_worker_configured")
        _init_worker_logging(str(log_path), "INFO")
        assert any(isinstance(h, logging.FileHandler) for h in root.handlers)
        # Idempotent: a second call does not double-add.
        n = len(root.handlers)
        _init_worker_logging(str(log_path), "INFO")
        assert len(root.handlers) == n
    finally:
        root.handlers = saved
        if saved_flag:
            root._qallm_worker_configured = saved_flag
        elif hasattr(root, "_qallm_worker_configured"):
            delattr(root, "_qallm_worker_configured")
