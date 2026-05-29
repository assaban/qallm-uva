"""API router: verification endpoints.

Split from the former monolithic api/main.py. Shares the app's session
store and helpers via qallm.api.core. Behaviour is unchanged; only the
file boundary moved.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from qallm.api.core import (
    MODEL_CATALOG,
    check_model_available,
    get_state,
    model_label,
    parse_model_id,
    sessions,
)
from qallm.config import settings
from qallm.jobs import JobConflictError, JobStatus, get_store
from qallm.orchestrator import QALLMOrchestrator, LLM_PROVIDERS

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/verification/functions/{session_id}")
async def get_functions(session_id: str):
    state = get_state(session_id)
    from qallm.verification.extractor import extract_functions_from_source

    function_list = []
    for unit in state["units"]:
        name = unit.original_path.name
        repaired = state.get("repaired_units", {}).get(name)
        source = repaired.repaired_code_unit.source_code if repaired else unit.source_code

        funcs = extract_functions_from_source(source, name)
        for f in funcs:
            function_list.append({
                "name": f.name,
                "file": name,
                "lineno": f.lineno,
                "args": [{"name": a[0], "type": a[1]} for a in f.args],
                "docstring": f.docstring,
            })
    return {"functions": function_list}


def _run_verification_work(sid: str) -> dict:
    """Synchronous body of the verification step.

    Calls ``orch.run(source_path)`` which executes the full v3 loop:
    Baseline → N rounds of (repair → analyse → verify → profile → judge),
    with budget caps enforced at round boundaries and per-unit lineage
    tracking for accept/abandon decisions.

    Returns a result payload with both the legacy ``functions`` list (for
    back-compat with the existing UI) and the new v3 fields (tracks,
    judge verdicts, halt reason, budget summary).
    """
    state = get_state(sid)
    orch: QALLMOrchestrator = state["orchestrator"]
    source_path = state.get("source_path")
    if not source_path:
        raise RuntimeError(
            "Session has no source_path; cannot run the v3 loop. "
            "This indicates a session created before NEW-08 plumbed it through."
        )

    # The orchestrator owns the full loop, including ingestion, baseline,
    # rounds, judging, and persistence. It writes summary.json + views to
    # its reporter directory and returns the summary dict.
    summary = orch.run(source_path)

    # Cache for the stats endpoint to read later.
    state["verification_sessions"] = summary.get("sessions", [])
    state["last_summary"] = summary
    # Cache the full LLM transcript (prompts + responses, role-tagged) and
    # the report dir so the observability endpoint can serve per-round
    # improvement deltas and the prompts for the UI.
    state["transcript"] = orch.transcript.to_list()
    state["report_dir"] = str(orch.reporter.report_dir)

    # The UI expects a `functions` list with per-function rollup numbers
    # (legacy shape). Build it from the sessions in the summary.
    sessions_data = summary.get("sessions", [])
    total_bugs = sum(s.get("final_bugs", 0) for s in sessions_data)

    return {
        "session_id": sid,
        "total_bugs": total_bugs,
        "total_functions": len(sessions_data),
        "functions": sessions_data,
        "model": summary.get("model"),
        "repair_model": summary.get("repair_model"),
        "testgen_model": summary.get("testgen_model"),
        "oracle": summary.get("oracle"),
        "rounds_per_function": summary.get("rounds_per_function"),
        "token_usage": summary.get("cost", {}),
        # New v3 surface: full per-unit tracks, judge strategy, halt reason,
        # budget summary, test-stability summary.
        "tracks": summary.get("tracks", {}),
        "rounds_accepted_total": summary.get("rounds_accepted_total", 0),
        "rounds_abandoned_total": summary.get("rounds_abandoned_total", 0),
        "judge_strategy": summary.get("judge_strategy"),
        "halt_reason": summary.get("halt_reason"),
        "budget": summary.get("budget", {}),
        "test_persistence": summary.get("test_persistence", {}),
        # Path to the session directory so the frontend can deep-link the
        # generated report.html if it wants.
        "report_dir": str(orch.reporter.report_dir),
    }


@router.post("/api/verification/run")
async def run_verification(req: dict):
    """Submit the verification step as a background job.

    Returns immediately with a job_id; the frontend polls
    ``GET /api/jobs/{job_id}`` for status and the final result.

    Only one active job per session at a time. Submitting while another
    job is running for the same session returns 409.
    """
    sid = req.get("session_id", "")
    # Validate the session exists before submitting; _get_state raises 404
    # if not, which we want surfaced eagerly rather than from the worker.
    get_state(sid)

    store = get_store()
    try:
        job = await store.submit_sync(
            session_id=sid,
            kind="verification",
            work=lambda: _run_verification_work(sid),
        )
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {"job_id": job.job_id, "session_id": sid, "status": job.status.value}


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    """Return the current status of a background job, plus live progress.

    Beyond the bare job-store fields (status, timestamps, result, error),
    this enriches the response with a ``progress`` block sourced from the
    orchestrator's :meth:`snapshot` method when the job is for a session
    whose orchestrator is currently running.

    The progress block is the right place for the UI to render a live
    status: phase, current round / total rounds, current stage (analyse
    / repair / verify / judge), the unit currently being processed,
    cumulative accepted and abandoned variant counts, and budget consumed.

    Designed for *display*, not control. Fields are descriptive and
    coarse-grained on purpose: we don't try to compute a percentage,
    because LLM call durations and judge-driven early-halt make any
    percentage estimate misleading.
    """
    store = get_store()
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    payload = job.to_dict()

    # Attach a progress snapshot when we can. The job carries a session id;
    # the session holds the orchestrator that is doing the work.
    sid = payload.get("session_id")
    if sid and sid in sessions:
        orch = sessions[sid].get("orchestrator")
        if orch is not None:
            if not hasattr(orch, "snapshot"):
                # Orchestrator predates the progress API. Don't spam the
                # logs on every poll; just silently omit the progress block.
                # If you see this comment in production, your container is
                # running stale code: rebuild and clear __pycache__.
                pass
            else:
                try:
                    payload["progress"] = orch.snapshot().to_dict()
                except Exception as e:
                    # Real failure (not just a stale build). Log once per
                    # job so we have a breadcrumb without flooding the log.
                    logger.warning(
                        "Could not capture progress for job %s: %s",
                        job_id, e,
                    )
    return payload


@router.get("/api/session/{session_id}/jobs")
async def list_session_jobs(session_id: str):
    """List all jobs ever submitted for a session, most recent first."""
    store = get_store()
    jobs = await store.list_for_session(session_id)
    jobs_sorted = sorted(jobs, key=lambda j: j.created_at, reverse=True)
    return {"jobs": [j.to_dict() for j in jobs_sorted]}


