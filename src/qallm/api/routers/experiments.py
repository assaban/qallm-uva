"""API router: HumanEvalFix experiment results.

Makes historical experiment runs accessible and auditable through the
Web-UI. Each run is a directory under QALLM_RUNS_DIR containing the
artefacts the runner writes: manifest.json (parameters), aggregates.json
(per-strategy/model headline numbers), results.jsonl (one line per
problem), and report.md.

This router only reads those artefacts; it never launches a run (full
experiments take hours and download datasets, so they run from the CLI in
the user's environment, not from a web request). The endpoints:

  GET /api/experiments               list runs with a manifest summary
  GET /api/experiments/{run}         one run: manifest + aggregates
  GET /api/experiments/{run}/results per-problem detail (results.jsonl)
  GET /api/experiments/{run}/report  the markdown report text
"""

from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, HTTPException

from qallm.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _runs_dir() -> str:
    return settings.QALLM_RUNS_DIR


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _read_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


def _is_run_dir(path: str) -> bool:
    """A run directory is one that has at least a manifest or results file."""
    return (
        os.path.isfile(os.path.join(path, "manifest.json"))
        or os.path.isfile(os.path.join(path, "results.jsonl"))
    )


@router.get("/api/experiments")
async def list_experiments():
    """List experiment runs with a compact summary for each.

    Degrades gracefully: an empty list when the runs directory does not
    exist or holds no runs, so the UI shows an empty state rather than an
    error.
    """
    runs_dir = _runs_dir()
    if not os.path.isdir(runs_dir):
        return {"runs_dir": runs_dir, "runs": []}

    runs = []
    for name in sorted(os.listdir(runs_dir), reverse=True):
        run_path = os.path.join(runs_dir, name)
        if not os.path.isdir(run_path) or not _is_run_dir(run_path):
            continue
        manifest = _read_json(os.path.join(run_path, "manifest.json")) or {}
        aggregates = _read_json(os.path.join(run_path, "aggregates.json")) or []
        # results.jsonl can be large; just count lines for the summary.
        results_path = os.path.join(run_path, "results.jsonl")
        n_results = 0
        if os.path.isfile(results_path):
            try:
                with open(results_path, encoding="utf-8") as fh:
                    n_results = sum(1 for line in fh if line.strip())
            except OSError:
                n_results = 0
        runs.append({
            "id": name,
            "models": manifest.get("models", []),
            "strategies": manifest.get("strategies", []),
            "rounds": manifest.get("rounds"),
            "sample_size": manifest.get("sample_size"),
            "created": manifest.get("started_at") or manifest.get("created"),
            "n_results": n_results,
            "n_combinations": len(aggregates),
            "has_report": os.path.isfile(os.path.join(run_path, "report.md")),
        })
    return {"runs_dir": runs_dir, "runs": runs}


def _run_path_or_404(run_id: str) -> str:
    # Guard against path traversal: run_id must be a single path segment.
    if "/" in run_id or "\\" in run_id or run_id in ("", ".", ".."):
        raise HTTPException(status_code=400, detail="Invalid run id")
    run_path = os.path.join(_runs_dir(), run_id)
    if not os.path.isdir(run_path) or not _is_run_dir(run_path):
        raise HTTPException(status_code=404, detail="Experiment run not found")
    return run_path


@router.get("/api/experiments/{run_id}")
async def get_experiment(run_id: str):
    """One run: manifest parameters plus the per-(strategy, model) aggregates."""
    run_path = _run_path_or_404(run_id)
    return {
        "id": run_id,
        "manifest": _read_json(os.path.join(run_path, "manifest.json")) or {},
        "aggregates": _read_json(os.path.join(run_path, "aggregates.json")) or [],
        "has_report": os.path.isfile(os.path.join(run_path, "report.md")),
    }


@router.get("/api/experiments/{run_id}/results")
async def get_experiment_results(run_id: str):
    """Per-problem results for a run (the parsed results.jsonl)."""
    run_path = _run_path_or_404(run_id)
    return {"id": run_id,
            "results": _read_jsonl(os.path.join(run_path, "results.jsonl"))}


@router.get("/api/experiments/{run_id}/report")
async def get_experiment_report(run_id: str):
    """The markdown report text for a run, for inline display/download."""
    run_path = _run_path_or_404(run_id)
    report_path = os.path.join(run_path, "report.md")
    if not os.path.isfile(report_path):
        raise HTTPException(status_code=404, detail="No report.md for this run")
    try:
        with open(report_path, encoding="utf-8") as fh:
            return {"id": run_id, "markdown": fh.read()}
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
