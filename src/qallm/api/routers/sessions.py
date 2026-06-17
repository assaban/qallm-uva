"""API router: sessions endpoints.

Split from the former monolithic api/main.py. Shares the app's session
store and helpers via qallm.api.core. Behaviour is unchanged; only the
file boundary moved.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from qallm.api.core import (
    model_label,
    parse_model_id,
    sessions,
)
from qallm.orchestrator import QALLMOrchestrator
from qallm.ingestion.ingestion_manager import IngestionManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/session/upload")
async def upload_session(
    archives: List[UploadFile] = File(...),
    stage: str = Form("implementation"),
    strategy: str = Form("rl"),
    model: str = Form("openai:gpt-4o-mini"),
    oracle: str = Form("crash"),
    rounds: int = Form(5),
    # Separate models for repair and test generation. Optional: when None,
    # both inherit the session default `model`.
    repair_model: Optional[str] = Form(None),
    testgen_model: Optional[str] = Form(None),
    # Judge strategy (NEW-02): which strategy decides accept/abandon.
    judge_strategy: str = Form("lexicographic"),
    # Test stability (NEW-01).
    test_stability: str = Form("frozen"),
    generation_policy: str = Form("grow"),
    # Budget caps (NEW-05). All optional; orchestrator fills sensible defaults.
    max_tokens: Optional[int] = Form(None),
    max_seconds: Optional[float] = Form(None),
    max_round_seconds: Optional[float] = Form(None),
    max_cost_usd: Optional[float] = Form(None),
    # Optional custom tags/names for grouping and retrieving sessions,
    # supplied as a comma-separated string (e.g. "thesis,baseline,run-3").
    tags: str = Form(""),
):
    """Upload files, create session, initialise orchestrator.

    Accepts the full v1 configuration surface: separate models for repair
    and test generation, judge strategy, test stability, budget caps. All
    advanced settings are optional with sensible defaults; the basic flow
    works with just ``model``, ``oracle``, and ``rounds`` as before.
    """
    # Write uploads to /tmp to avoid triggering uvicorn --reload.
    upload_root = Path(tempfile.mkdtemp(prefix="qallm_upload_"))

    for archive in archives:
        file_path = upload_root / archive.filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(archive.file, buffer)
        if zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path, "r") as z:
                z.extractall(upload_root / "extracted")

    target = str(upload_root / "extracted") if (upload_root / "extracted").exists() else str(upload_root)

    session_id = str(uuid.uuid4())
    llm_type, model_name = parse_model_id(model)

    # Resolve separate models. None means "inherit default."
    repair_llm_type, repair_model_name = (None, None)
    if repair_model:
        repair_llm_type, repair_model_name = parse_model_id(repair_model)

    testgen_llm_type, testgen_model_name = (None, None)
    if testgen_model:
        testgen_llm_type, testgen_model_name = parse_model_id(testgen_model)

    # Build budget caps if any cap field was supplied; otherwise let the
    # orchestrator construct defaults from `rounds` alone.
    caps = None
    if any(v is not None for v in (max_tokens, max_seconds, max_round_seconds, max_cost_usd)):
        from qallm.cost import BudgetCaps
        cap_kwargs = {"max_rounds": rounds}
        # `BudgetCaps.from_kwargs` treats 0 or negative as "unset"; we pass
        # only fields the caller explicitly supplied to avoid overriding
        # a sensible default with None.
        if max_tokens is not None:
            cap_kwargs["max_tokens"] = max_tokens
        if max_seconds is not None:
            cap_kwargs["max_seconds"] = max_seconds
        if max_round_seconds is not None:
            cap_kwargs["max_round_seconds"] = max_round_seconds
        if max_cost_usd is not None:
            cap_kwargs["max_cost_usd"] = max_cost_usd
        caps = BudgetCaps.from_kwargs(**cap_kwargs)

    try:
        # The session's UUID doubles as the reporter's run_id. This pins the
        # output directory to one location for the entire session, no matter
        # how many times the orchestrator's `run()` is invoked, and is the
        # right fix against the "multiple datetime folders per session" bug.
        # A short timestamp prefix is included for human readability when
        # browsing the outputs/ directory.
        run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{session_id[:8]}"
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        orchestrator = QALLMOrchestrator(
            stage=stage,
            strategy=strategy,
            llm_type=llm_type,
            model_name=model_name,
            oracle=oracle,
            rounds=rounds,
            test_stability=test_stability,
            generation_policy=generation_policy,
            judge_strategy=judge_strategy,
            caps=caps,
            repair_llm_type=repair_llm_type,
            repair_model_name=repair_model_name,
            testgen_llm_type=testgen_llm_type,
            testgen_model_name=testgen_model_name,
            run_id=run_id,
            tags=tag_list,
            origin="interactive",
        )
        units = orchestrator.ingestion_manager.collect(target)

        sessions[session_id] = {
            "orchestrator": orchestrator,
            "units": units,
            "analysed_units": {},
            "repaired_units": {},
            "analysis_rounds": [],
            "source_path": target,
            "config": {
                "stage": stage,
                "strategy": strategy,
                "model_id": model,
                "llm_type": llm_type,
                "model_name": model_name,
                "model_label": model_label(model),
                "repair_model_id": repair_model or model,
                "repair_model_label": model_label(repair_model or model),
                "testgen_model_id": testgen_model or model,
                "testgen_model_label": model_label(testgen_model or model),
                "oracle": oracle,
                "rounds": rounds,
                "judge_strategy": judge_strategy,
                "test_stability": test_stability,
                "generation_policy": generation_policy,
                "max_tokens": max_tokens,
                "max_seconds": max_seconds,
                "max_round_seconds": max_round_seconds,
                "max_cost_usd": max_cost_usd,
            },
        }

        return {
            "session_id": session_id,
            "files": [u.original_path.name for u in units],
            "model": sessions[session_id]["config"]["model_label"],
            "config": sessions[session_id]["config"],
        }
    except Exception as e:
        logger.error("Ingestion failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/session/ingest")
async def ingest_source(req: dict):
    source_path = req.get("source_path", "")
    model = req.get("model_name", "openai:gpt-4o-mini")
    llm_type, model_name = parse_model_id(model)

    session_id = str(uuid.uuid4())
    try:
        # Ingestion has no dependency on the orchestrator (no LLM, no
        # reporter): collect with a standalone IngestionManager. The
        # orchestrator, configured for the downstream analyse/repair stages,
        # is built once and stored on session state. Building it is cheap
        # (LLM clients are created lazily on first use, not here), so this
        # keeps ingestion decoupled without delaying the later stages.
        units = IngestionManager().collect(source_path)
        orchestrator = QALLMOrchestrator(
            stage=req.get("stage", "implementation"),
            strategy=req.get("strategy", "rl"),
            llm_type=llm_type,
            model_name=model_name,
            oracle=req.get("oracle", "crash"),
            rounds=req.get("rounds", 5),
            tags=req.get("tags") or [],
            origin="interactive",
        )

        sessions[session_id] = {
            "orchestrator": orchestrator,
            "units": units,
            "analysed_units": {},
            "repaired_units": {},
            "analysis_rounds": [],
            "config": req,
        }
        return {"session_id": session_id, "files": [u.original_path.name for u in units]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

