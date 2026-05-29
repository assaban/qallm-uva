"""API router: repair endpoints.

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


@router.post("/api/repair/{session_id}")
async def run_repair(session_id: str, req: dict = None):
    state = get_state(session_id)
    orch: QALLMOrchestrator = state["orchestrator"]

    patches = []
    for name, analysed_unit in state["analysed_units"].items():
        repaired = orch.repair_manager.repair_code_unit(analysed_unit)
        state["repaired_units"][name] = repaired
        res = repaired.repaired_result

        diff = res.unified_diff if res else ""
        patches.append({
            "finding_id": name,
            "applied": res.compiles if res else False,
            "description": res.explanation if res else "No repair attempted",
            "unified_diff": diff,
            "error": res.validation_error if res else None,
            "meta": {"file": name, "model": orch.llm.name()},
        })

    return {
        "patches": patches,
        "repaired_count": sum(1 for p in patches if p["applied"]),
        "token_usage": orch.tracker.to_dict(),
        "provider_used": orch.llm.name(),
        "repair_round": len(state.get("analysis_rounds", [])),
    }


@router.get("/api/session/{session_id}/diff/{filename}")
async def get_diff(session_id: str, filename: str):
    state = get_state(session_id)
    repaired = state.get("repaired_units", {}).get(filename)
    if repaired and repaired.repaired_result:
        return {"diff": repaired.repaired_result.unified_diff}
    return {"diff": ""}


@router.get("/api/session/{session_id}/versions")
async def get_versions(session_id: str):
    state = get_state(session_id)
    versions = [{"round": 0, "label": "Baseline (original)", "files": len(state["units"])}]
    n_repaired = len(state.get("repaired_units", {}))
    if n_repaired > 0:
        versions.append({"round": 1, "label": "After repair", "files": n_repaired})
    return {"versions": versions}


