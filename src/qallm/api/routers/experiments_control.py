"""API router: experiment catalog and run control.

Complements the read-only experiments router (which browses historical
runs) with the ability to see what experiments are available and to launch
a new run from the UI with live progress.

Launching is real work: a run downloads its dataset from Hugging Face and
calls LLMs, so it needs network access and credentials, and a full run
takes hours. The launch endpoint therefore submits the run as a background
job (reusing the job store) and streams progress via a per-run progress
registry the runner updates through its on_problem_complete callback. The
UI polls the progress endpoint, the same shape as a terminal would show:
which problem just finished, how many done, the running tallies.

  GET  /api/experiment-catalog            available experiments (metadata)
  POST /api/experiment-catalog/{id}/run   launch a run, returns job + run id
  GET  /api/experiment-runs/{run}/progress live progress for a launched run
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from qallm.jobs import JobConflictError, get_store
from qallm.config import settings
from qallm.experiments.catalog import get_experiment, list_experiments

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Progress registry: a launched run reports per-problem completion here, and
# the progress endpoint reads it. Keyed by run id. Thread-safe because the
# background job runs in a worker thread.
# ---------------------------------------------------------------------------

class RunProgress:
    """Live progress for one experiment run."""

    def __init__(self, run_id: str, total: int) -> None:
        self.run_id = run_id
        self.total = total
        self.completed = 0
        self.bug_detected = 0
        self.repair_successful = 0
        self.errored = 0
        # A short tail of recent per-problem lines, like terminal output.
        self.log: list[dict] = []
        self.status = "running"   # running | done | failed
        self.error: str | None = None
        self.started_at = time.time()
        self.finished_at: float | None = None
        self._lock = threading.Lock()

    def record(self, result: dict) -> None:
        with self._lock:
            self.completed += 1
            if result.get("error"):
                self.errored += 1
            else:
                if result.get("bug_detected"):
                    self.bug_detected += 1
                if result.get("repair_successful"):
                    self.repair_successful += 1
            line = {
                "task_id": result.get("task_id"),
                "strategy": result.get("strategy"),
                "model": result.get("model"),
                "bug_detected": result.get("bug_detected"),
                "repair_successful": result.get("repair_successful"),
                "error": result.get("error"),
                "at": time.time(),
            }
            # Keep the last 100 lines so the registry stays bounded.
            self.log.append(line)
            if len(self.log) > 100:
                self.log = self.log[-100:]

    def finish(self, error: str | None = None) -> None:
        with self._lock:
            self.status = "failed" if error else "done"
            self.error = error
            self.finished_at = time.time()

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "run_id": self.run_id,
                "status": self.status,
                "total": self.total,
                "completed": self.completed,
                "bug_detected": self.bug_detected,
                "repair_successful": self.repair_successful,
                "errored": self.errored,
                "log": list(self.log),
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            }


_progress: dict[str, RunProgress] = {}
_progress_lock = threading.Lock()


def _put_progress(p: RunProgress) -> None:
    with _progress_lock:
        _progress[p.run_id] = p


def _get_progress(run_id: str) -> RunProgress | None:
    with _progress_lock:
        return _progress.get(run_id)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

@router.get("/api/experiment-catalog")
async def experiment_catalog():
    """List available experiments with their dataset/citation metadata."""
    return {"experiments": [e.to_dict() for e in list_experiments()]}


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

def _run_experiment_work(run_id: str, spec_id: str, params: dict) -> dict:
    """Background work: run the experiment, updating the progress registry.

    Imported lazily so the experiments extra (datasets) is only needed when
    a run is actually launched, not at import time.
    """
    from qallm.experiments.humaneval_runner import ExperimentConfig, run_experiment

    progress = _get_progress(run_id)

    def on_complete(result) -> None:
        # ProblemResult is a dataclass; normalise to dict for the registry.
        from dataclasses import asdict, is_dataclass
        d = asdict(result) if is_dataclass(result) else dict(result)
        if progress:
            progress.record(d)

    config = ExperimentConfig(
        output_dir=Path(settings.QALLM_RUNS_DIR) / run_id,
        models=params["models"],
        strategies=params["strategies"],
        sample_size=params.get("sample_size"),
        seed=params.get("seed", 0),
        rounds=params.get("rounds", 5),
        oracle=params.get("oracle", "crash"),
        judge_strategy=params.get("judge_strategy", "lexicographic"),
    )
    try:
        results = run_experiment(config, on_problem_complete=on_complete)
        if progress:
            progress.finish()
        return {"run_id": run_id, "n_results": len(results)}
    except Exception as exc:  # noqa: BLE001 - surface to the job + progress
        if progress:
            progress.finish(error=str(exc))
        raise


@router.post("/api/experiment-catalog/{experiment_id}/run")
async def launch_experiment(experiment_id: str, req: dict):
    """Launch an experiment run as a background job.

    Body: {models: [...], strategies: [...], sample_size?, seed?, rounds?,
    oracle?, judge_strategy?}. Returns the run id (also the run directory
    name) and a job id; poll /api/experiment-runs/{run}/progress for live
    status and /api/experiments/{run} for the final artefacts.
    """
    spec = get_experiment(experiment_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown experiment")

    models = req.get("models") or []
    strategies = req.get("strategies") or []
    if not models or not strategies:
        raise HTTPException(status_code=400,
                            detail="models and strategies are required")

    sample_size = req.get("sample_size")
    # Estimate total problem-combinations for the progress bar.
    n_problems = sample_size if sample_size else spec.n_problems
    total = n_problems * len(strategies) * len(models)

    run_id = f"{experiment_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    _put_progress(RunProgress(run_id, total))

    params = {
        "models": models,
        "strategies": strategies,
        "sample_size": sample_size,
        "seed": req.get("seed", 0),
        "rounds": req.get("rounds", 5),
        "oracle": req.get("oracle", "crash"),
        "judge_strategy": req.get("judge_strategy", "lexicographic"),
    }

    store = get_store()
    try:
        job = await store.submit_sync(
            session_id=run_id,         # the run id keys the job
            kind="experiment",
            work=lambda: _run_experiment_work(run_id, experiment_id, params),
        )
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {"run_id": run_id, "job_id": job.job_id, "status": job.status.value}


@router.get("/api/experiment-runs/{run_id}/progress")
async def experiment_progress(run_id: str):
    """Live progress for a launched run.

    Returns the registry snapshot if the run was launched in this process.
    Falls back to a not-tracked response otherwise (e.g. a CLI run, or
    after a server restart); the historical artefacts remain available via
    the experiments browse endpoints.
    """
    p = _get_progress(run_id)
    if p is None:
        return {"run_id": run_id, "tracked": False}
    snap = p.to_dict()
    snap["tracked"] = True
    return snap


# ---------------------------------------------------------------------------
# Dataset through the pipeline
# ---------------------------------------------------------------------------

@router.post("/api/experiment-catalog/{experiment_id}/to-pipeline")
async def dataset_to_pipeline(experiment_id: str, req: dict):
    """Load an experiment's dataset into the normal pipeline.

    Instead of the experiment runner, this materialises the dataset's buggy
    programs as .py files in a directory and creates a standard pipeline
    session over that directory, so the whole dataset flows through QALLM
    exactly like any other uploaded code. The returned session_id behaves
    like any other: configure and run it from the pipeline, browse it in
    the session library.

    Body: {sample_size?, seed?, model?, strategy?, oracle?, rounds?, tags?}.
    """
    spec = get_experiment(experiment_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown experiment")

    # Lazy import: datasets extra only needed when this is actually called.
    try:
        from qallm.experiments.humaneval_dataset import load_humanevalfix
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Could not load the experiments module: {exc}",
        ) from exc

    sample_size = req.get("sample_size")
    seed = req.get("seed", 0)
    try:
        problems = load_humanevalfix(sample_size=sample_size, seed=seed)
    except Exception as exc:  # noqa: BLE001 - dataset download can fail
        raise HTTPException(
            status_code=502,
            detail=(f"Could not load the dataset ({spec.dataset_id}): {exc}. "
                    "A network connection is required."),
        ) from exc

    materialised = _materialise_problems(problems)
    session_id = _create_pipeline_session(materialised, req, experiment_id)
    return {
        "session_id": session_id,
        "experiment_id": experiment_id,
        "n_files": len(problems),
        "directory": materialised,
    }


def _materialise_problems(problems: list) -> str:
    """Write each problem's buggy program to its own .py file, return the dir."""
    import tempfile

    out = Path(tempfile.mkdtemp(prefix="qallm_dataset_"))
    for p in problems:
        # task_id like "Python/0" -> a safe file name.
        safe = p.task_id.replace("/", "_")
        (out / f"{safe}.py").write_text(p.buggy_full_source, encoding="utf-8")
    return str(out)


def _create_pipeline_session(directory: str, req: dict, experiment_id: str) -> str:
    """Create a normal pipeline session over a directory of programs."""
    import uuid

    from qallm.api.core import parse_model_id, sessions
    from qallm.orchestrator import QALLMOrchestrator

    model = req.get("model", "openai:gpt-4o-mini")
    llm_type, model_name = parse_model_id(model)
    tags = req.get("tags") or [experiment_id, "dataset"]

    session_id = str(uuid.uuid4())
    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{session_id[:8]}"
    orchestrator = QALLMOrchestrator(
        stage=req.get("stage", "implementation"),
        strategy=req.get("strategy", "feedback"),
        llm_type=llm_type,
        model_name=model_name,
        oracle=req.get("oracle", "crash"),
        rounds=req.get("rounds", 5),
        run_id=run_id,
        tags=tags,
    )
    units = orchestrator.ingestion_manager.collect(directory)
    sessions[session_id] = {
        "orchestrator": orchestrator,
        "units": units,
        "analysed_units": {},
        "repaired_units": {},
        "analysis_rounds": [],
        "config": req,
    }
    return session_id
