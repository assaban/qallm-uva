"""API router: session library.

QALLM is a research tool, so being able to load every session the pipeline
has ever processed, with its results and report, is valuable. Each
orchestrator run writes a report directory under QALLM_SESSIONS_DIR
(summary.json plus the lineage/abandoned round artefacts). This router
indexes those directories and serves them read-only.

This is distinct from the in-memory ``sessions`` dict in core.py, which
holds *live* sessions for the current server process. The library here is
the durable, on-disk history that survives restarts.

  GET /api/library                  list processed sessions (summary)
  GET /api/library/{session}        one session's full summary.json
  GET /api/library/{session}/report the session's report.md
"""

from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, HTTPException

from qallm.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _sessions_dir() -> str:
    return settings.QALLM_SESSIONS_DIR


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _is_session_dir(path: str) -> bool:
    """A session directory is one that has a summary.json."""
    return os.path.isfile(os.path.join(path, "summary.json"))


def _summarise(session_id: str, summary: dict) -> dict:
    """Compact card for the session list, derived from summary.json."""
    profile = summary.get("profile") or {}
    cost = summary.get("cost") or {}
    return {
        "id": session_id,
        "source": summary.get("source"),
        "strategy": summary.get("strategy"),
        "model": summary.get("model"),
        "profile_id": profile.get("profile_id"),
        "lifecycle_stage": summary.get("lifecycle_stage"),
        "oracle": summary.get("oracle"),
        "rounds_per_function": summary.get("rounds_per_function"),
        "units_analyzed": summary.get("units_analyzed"),
        "functions_verified": summary.get("functions_verified"),
        "rounds_accepted_total": summary.get("rounds_accepted_total"),
        "rounds_abandoned_total": summary.get("rounds_abandoned_total"),
        "total_cost_usd": cost.get("total_cost_usd"),
        "halt_reason": summary.get("halt_reason"),
    }


@router.get("/api/library")
async def list_sessions():
    """List every processed session with a compact summary card.

    Empty list when the sessions directory does not exist, so the UI shows
    an empty state rather than an error.
    """
    base = _sessions_dir()
    if not os.path.isdir(base):
        return {"sessions_dir": base, "sessions": []}

    sessions = []
    for name in sorted(os.listdir(base), reverse=True):
        path = os.path.join(base, name)
        if not os.path.isdir(path) or not _is_session_dir(path):
            continue
        summary = _read_json(os.path.join(path, "summary.json")) or {}
        card = _summarise(name, summary)
        card["has_report"] = os.path.isfile(os.path.join(path, "report.md"))
        sessions.append(card)
    return {"sessions_dir": base, "sessions": sessions}


def _session_path_or_404(session_id: str) -> str:
    # Guard against path traversal: session id must be one path segment.
    if "/" in session_id or "\\" in session_id or session_id in ("", ".", ".."):
        raise HTTPException(status_code=400, detail="Invalid session id")
    path = os.path.join(_sessions_dir(), session_id)
    if not os.path.isdir(path) or not _is_session_dir(path):
        raise HTTPException(status_code=404, detail="Session not found")
    return path


@router.get("/api/library/{session_id}")
async def get_session(session_id: str):
    """One session's full summary.json (profile, tracks, sessions, cost)."""
    path = _session_path_or_404(session_id)
    summary = _read_json(os.path.join(path, "summary.json")) or {}
    return {
        "id": session_id,
        "summary": summary,
        "has_report": os.path.isfile(os.path.join(path, "report.md")),
    }


@router.get("/api/library/{session_id}/report")
async def get_session_report(session_id: str):
    """The session's report.md text, for inline display/download."""
    path = _session_path_or_404(session_id)
    report_path = os.path.join(path, "report.md")
    if not os.path.isfile(report_path):
        raise HTTPException(status_code=404, detail="No report.md for this session")
    try:
        with open(report_path, encoding="utf-8") as fh:
            return {"id": session_id, "markdown": fh.read()}
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
