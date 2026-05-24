"""QALLM Web API: FastAPI backend for the research pipeline UI.

Endpoints map to the 6-step pipeline:
  Step 0: POST /api/session/upload       Upload files + init orchestrator
  Step 1: POST /api/analyse              Run static analysis
  Step 2: POST /api/repair/{sid}         LLM-based code repair
  Step 3: POST /api/verification/run     RL-guided test generation
  Step 4: GET  /api/session/{sid}/stats  Full experiment statistics
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from qallm.config import settings
from qallm.jobs import JobConflictError, JobStatus, get_store
from qallm.orchestrator import QALLMOrchestrator, LLM_PROVIDERS

logger = logging.getLogger(__name__)

app = FastAPI(title="QALLM Research Pipeline", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions: Dict[str, Dict] = {}

# ─── Model registry: provider:model_id → (llm_type, model_id, available) ───
MODEL_CATALOG = [
    # {"id": "ollama:gemma4:31b",         "provider": "ollama",    "model": "gemma4:31b",        "label": "Ollama / 31B (Dense) (local)"},
    # {"id": "ollama:gemma4:26b",         "provider": "ollama",    "model": "gemma4:26b",        "label": "Ollama / 26B (Mixture Experts & 4B (local)"},
    {"id": "ollama:gemma4:e4b",         "provider": "ollama",    "model": "gemma4:e4b",        "label": "Ollama / Effective 4B (E4B) (local)"},
    {"id": "ollama:gemma3:4b",         "provider": "ollama",    "model": "gemma3:4b",        "label": "Ollama / Gemma3 4B (local)"},
    {"id": "ollama:gemma2",            "provider": "ollama",    "model": "gemma2",           "label": "Ollama / Gemma2 (local)"},
    {"id": "openai:gpt-4o-mini",      "provider": "openai",    "model": "gpt-4o-mini",      "label": "OpenAI / gpt-4o-mini"},
    {"id": "openai:gpt-5.4-mini",     "provider": "openai",    "model": "gpt-5.4-mini",     "label": "OpenAI / gpt-5.4-mini"},
    {"id": "openai:gpt-5-mini",       "provider": "openai",    "model": "gpt-5-mini",       "label": "OpenAI / gpt-5-mini"},
    {"id": "openai:gpt-5.4",          "provider": "openai",    "model": "gpt-5.4",          "label": "OpenAI / gpt-5.4"},
    {"id": "anthropic:claude-haiku-4.5", "provider": "anthropic", "model": "claude-haiku-4-5-20251001", "label": "Anthropic / Claude Haiku 4.5"},
    {"id": "anthropic:claude-sonnet-4",  "provider": "anthropic", "model": "claude-sonnet-4-20250514",  "label": "Anthropic / Claude Sonnet 4"},
]


def _check_model_available(entry: dict) -> bool:
    provider = entry["provider"]
    if provider == "openai":
        return bool(settings.OPENAI_API_KEY)
    elif provider == "anthropic":
        return bool(settings.ANTHROPIC_API_KEY)
    elif provider == "ollama":
        return bool(settings.OLLAMA_BASE_URL)
    return False


def _parse_model_id(model_id: str) -> tuple[str, str]:
    """Parse 'provider:model' into (llm_type, model_name).
    Falls back to auto-detection if no colon present."""
    if ":" in model_id and not model_id.startswith("gemma"):
        # Handle provider:model format (but not ollama model names like gemma3:4b)
        parts = model_id.split(":", 1)
        if parts[0] in ("openai", "anthropic", "ollama"):
            return parts[0], parts[1]

    # Look up in catalog
    for entry in MODEL_CATALOG:
        if entry["id"] == model_id:
            return entry["provider"], entry["model"]

    # Auto-detect from name
    if model_id.startswith("gpt"):
        return "openai", model_id
    elif model_id.startswith("claude"):
        return "anthropic", model_id
    else:
        return "ollama", model_id


def _get_state(sid: str) -> dict:
    state = sessions.get(sid)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    return state


# ═══════════════════════════════════════════════
# Step 0: Session Initialization
# ═══════════════════════════════════════════════

@app.post("/api/session/upload")
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
):
    """Upload files, create session, initialise orchestrator.

    Accepts the full v1 configuration surface: separate models for repair
    and test generation, judge strategy, test stability, budget caps. All
    advanced settings are optional with sensible defaults; the basic flow
    works with just ``model``, ``oracle``, and ``rounds`` as before.
    """
    # Write uploads to /tmp to avoid triggering uvicorn --reload.
    upload_root = Path(tempfile.mkdtemp(prefix="qallm_upload_"))
    # upload_root = Path("/tmp/qallm_upload")

    logger.info(f"Upload ${len(archives)} archives to root directory: {upload_root}")

    for archive in archives:
        file_path = upload_root / archive.filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(archive.file, buffer)
        if zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path, "r") as z:
                z.extractall(upload_root / "extracted")

    target = str(upload_root / "extracted") if (upload_root / "extracted").exists() else str(upload_root)

    session_id = str(uuid.uuid4())
    llm_type, model_name = _parse_model_id(model)

    # Resolve separate models. None means "inherit default."
    repair_llm_type, repair_model_name = (None, None)
    if repair_model:
        repair_llm_type, repair_model_name = _parse_model_id(repair_model)

    testgen_llm_type, testgen_model_name = (None, None)
    if testgen_model:
        testgen_llm_type, testgen_model_name = _parse_model_id(testgen_model)

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
                "model_label": _model_label(model),
                "repair_model_id": repair_model or model,
                "repair_model_label": _model_label(repair_model or model),
                "testgen_model_id": testgen_model or model,
                "testgen_model_label": _model_label(testgen_model or model),
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


def _model_label(model_id: str) -> str:
    """Look up the human-readable label for a model id; fall back to id itself."""
    return next((e["label"] for e in MODEL_CATALOG if e["id"] == model_id), model_id)


@app.post("/api/session/ingest")
async def ingest_source(req: dict):
    source_path = req.get("source_path", "")
    model = req.get("model_name", "openai:gpt-4o-mini")
    llm_type, model_name = _parse_model_id(model)

    session_id = str(uuid.uuid4())
    try:
        orchestrator = QALLMOrchestrator(
            stage=req.get("stage", "implementation"),
            strategy=req.get("strategy", "rl"),
            llm_type=llm_type,
            model_name=model_name,
            oracle=req.get("oracle", "crash"),
            rounds=req.get("rounds", 5),
        )
        units = orchestrator.ingestion_manager.collect(source_path)

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


# ═══════════════════════════════════════════════
# Config endpoints
# ═══════════════════════════════════════════════

@app.get("/api/llm/providers")
async def get_providers():
    return {"configured": list(LLM_PROVIDERS.keys())}


@app.get("/api/verification/strategies")
async def get_strategies():
    return {"configured": ["rl", "oneshot", "hypothesis"]}


@app.get("/api/verification/models")
async def get_models():
    """Returns model catalog with availability status for the frontend dropdown."""
    result = []
    for entry in MODEL_CATALOG:
        available = _check_model_available(entry)
        result.append({
            "id": entry["id"],
            "label": entry["label"],
            "provider": entry["provider"],
            "available": available,
        })
    return {"models": result}


@app.get("/api/analysis/tools")
async def get_analysis_tools():
    return {"tools": ["bandit", "radon", "ruff", "trufflehog"]}


@app.get("/api/session/{session_id}/config")
async def get_session_config(session_id: str):
    """Returns the locked-in session configuration (model, strategy, oracle)."""
    state = _get_state(session_id)
    return {"config": state.get("config", {})}


# ═══════════════════════════════════════════════
# Step 1: Static Analysis
# ═══════════════════════════════════════════════

@app.post("/api/analyse")
async def run_analysis(req: dict):
    sid = req.get("session_id", "")
    selected_files = req.get("selected_files", [])
    selected_tools = req.get("selected_tools", [])

    state = _get_state(sid)
    orch: QALLMOrchestrator = state["orchestrator"]

    all_findings = []
    for unit in state["units"]:
        if unit.original_path.name in selected_files:
            analysed = orch.analysis_manager.analyse_code_unit(unit)
            state["analysed_units"][unit.original_path.name] = analysed
            all_findings.extend(analysed.findings)

    summary = {
        "total": len(all_findings),
        "by_severity": {
            s: len([f for f in all_findings if f.severity == s])
            for s in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        },
    }
    state["analysis_rounds"].append({"round": len(state["analysis_rounds"]), **summary})

    return {"findings": [asdict(f) for f in all_findings], "summary": summary}


@app.get("/api/session/{session_id}/analysis-history")
async def get_analysis_history(session_id: str):
    state = _get_state(session_id)
    return {"rounds": state.get("analysis_rounds", [])}


@app.get("/api/session/{session_id}/files")
async def get_session_files(session_id: str):
    state = _get_state(session_id)
    return {"files": [u.original_path.name for u in state["units"]]}


@app.get("/api/session/{session_id}/paper-metrics-history")
async def get_paper_metrics_history(session_id: str):
    """Metrics history across analysis rounds for the ReanalyseScreen table."""
    state = _get_state(session_id)
    rounds_data = []
    for i, ar in enumerate(state.get("analysis_rounds", [])):
        rounds_data.append({
            "round": i,
            "label": "Baseline" if i == 0 else f"Round {i}",
            "cs": ar.get("by_severity", {}).get("HIGH", 0) + ar.get("by_severity", {}).get("CRITICAL", 0),
            "mi": 0,  # Would need radon re-run for real MI
            "codu": 0,
            "code": 0,
            "loc": 0,
            "cc": ar.get("by_severity", {}).get("MEDIUM", 0),
        })
    return {"rounds": rounds_data}


@app.get("/api/session/{session_id}/comparisons")
async def get_comparisons(session_id: str):
    """Computes deltas between analysis rounds."""
    state = _get_state(session_id)
    rounds = state.get("analysis_rounds", [])
    comparisons = []
    for i in range(1, len(rounds)):
        prev = rounds[i - 1]
        curr = rounds[i]
        comparisons.append({
            "round": i,
            "vs_baseline": {
                "cs_delta": curr.get("total", 0) - rounds[0].get("total", 0),
                "mi_delta": 0,
                "codu_delta": 0,
                "code_delta": 0,
                "loc_delta": 0,
                "cc_delta": 0,
            },
            "vs_previous": {
                "cs_delta": curr.get("total", 0) - prev.get("total", 0),
            },
        })
    return {"comparisons": comparisons}


@app.get("/api/session/{session_id}/rounds")
async def get_rounds(session_id: str):
    """Lists all repair/analysis rounds for the round selector."""
    state = _get_state(session_id)
    rounds = []
    rounds.append({"round": 0, "label": "Baseline", "files": len(state["units"]), "has_findings": True, "has_tests": False})
    for i, ar in enumerate(state.get("analysis_rounds", []), 1):
        rounds.append({"round": i, "label": f"Round {i}", "files": len(state["units"]), "has_findings": True, "has_tests": False})
    if state.get("verification_sessions"):
        rounds[-1]["has_tests"] = True
    return {"rounds": rounds}


# ═══════════════════════════════════════════════
# Step 2: LLM Repair
# ═══════════════════════════════════════════════

@app.post("/api/repair/{session_id}")
async def run_repair(session_id: str, req: dict = None):
    state = _get_state(session_id)
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


@app.get("/api/session/{session_id}/diff/{filename}")
async def get_diff(session_id: str, filename: str):
    state = _get_state(session_id)
    repaired = state.get("repaired_units", {}).get(filename)
    if repaired and repaired.repaired_result:
        return {"diff": repaired.repaired_result.unified_diff}
    return {"diff": ""}


@app.get("/api/session/{session_id}/versions")
async def get_versions(session_id: str):
    state = _get_state(session_id)
    versions = [{"round": 0, "label": "Baseline (original)", "files": len(state["units"])}]
    n_repaired = len(state.get("repaired_units", {}))
    if n_repaired > 0:
        versions.append({"round": 1, "label": "After repair", "files": n_repaired})
    return {"versions": versions}


# ═══════════════════════════════════════════════
# Step 3: RL Verification
# ═══════════════════════════════════════════════

@app.get("/api/verification/functions/{session_id}")
async def get_functions(session_id: str):
    state = _get_state(session_id)
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
    state = _get_state(sid)
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


@app.post("/api/verification/run")
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
    _get_state(sid)

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


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    """Return the current status (and result, if done) of a background job."""
    store = get_store()
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job.to_dict()


@app.get("/api/session/{session_id}/jobs")
async def list_session_jobs(session_id: str):
    """List all jobs ever submitted for a session, most recent first."""
    store = get_store()
    jobs = await store.list_for_session(session_id)
    jobs_sorted = sorted(jobs, key=lambda j: j.created_at, reverse=True)
    return {"jobs": [j.to_dict() for j in jobs_sorted]}


# ═══════════════════════════════════════════════
# Step 4: Results / Stats / Export
# ═══════════════════════════════════════════════

@app.get("/api/session/{session_id}/stats")
async def get_stats(session_id: str):
    state = _get_state(session_id)
    orch: QALLMOrchestrator = state["orchestrator"]

    session_data = orch.verification_manager.get_session_data()
    analysis_rounds = state.get("analysis_rounds", [])
    config = state.get("config", {})

    total_bugs = sum(s.get("final_bugs", 0) for s in session_data)
    coverages = [s.get("final_coverage", 0) or 0 for s in session_data]
    avg_coverage = sum(coverages) / len(coverages) if coverages else 0

    testable = [s for s in session_data if (s.get("final_coverage") or 0) > 0]
    with_bugs = [s for s in testable if s.get("final_bugs", 0) > 0]
    fcr = len(with_bugs) / len(testable) if testable else 0

    n_findings = analysis_rounds[0]["total"] if analysis_rounds else 0
    n_repaired = sum(1 for r in state.get("repaired_units", {}).values()
                     if r.repaired_result and r.repaired_result.compiles)

    return {
        "config": config,
        "model": orch.llm.name(),
        "analysis": {"total_findings": n_findings, "rounds": analysis_rounds},
        "repair": {"files_repaired": n_repaired, "compile_rate": f"{n_repaired}/{len(state.get('repaired_units', {}))}"},
        "verification": {
            "total_functions": len(session_data),
            "total_bugs": total_bugs,
            "avg_coverage": round(avg_coverage, 1),
            "false_confidence_rate": round(fcr * 100, 1),
            "sessions": session_data,
        },
        "cost": orch.tracker.to_dict(),
    }


@app.get("/api/session/{session_id}/download/tests")
async def download_tests(session_id: str):
    state = _get_state(session_id)
    orch: QALLMOrchestrator = state["orchestrator"]

    files = []
    session_data = orch.verification_manager.get_session_data()
    for s in session_data:
        for r in s.get("rounds", []):
            gen = r.get("generated_test", {})
            if gen.get("is_valid") and gen.get("test_code"):
                files.append({
                    "name": f"test_{s.get('function_name', 'unknown')}_r{r.get('round_number', 0)}.py",
                    "content": gen["test_code"],
                })
    return {"files": files}


@app.get("/api/health")
async def health():
    return {
        "status": "online",
        "openai": bool(settings.OPENAI_API_KEY),
        "anthropic": bool(settings.ANTHROPIC_API_KEY),
        "sessions": len(sessions),
    }


# ─── Frontend static files ──────────────────────────────────────────
# In a built/deployed image we serve the React app from the same process
# as the API. The dist directory is created by the Docker frontend build
# stage. In a local dev setup it usually doesn't exist (the developer
# runs `vite dev` separately on :5173), so we mount only if present.
#
# Path resolution: if QALLM_FRONTEND_DIST is set (Docker), trust it.
# Otherwise compute from the source tree, which only works for editable
# installs (`pip install -e .`). A non-editable install must set the
# env var because __file__ then points to site-packages, not the repo.

_env_dist = os.getenv("QALLM_FRONTEND_DIST")
if _env_dist:
    _FRONTEND_DIST = Path(_env_dist)
else:
    # Editable / source-tree fallback: src/qallm/api/main.py -> repo root -> web/dist
    _FRONTEND_DIST = Path(__file__).resolve().parents[2].parent / "web" / "dist"

if _FRONTEND_DIST.is_dir():
    # html=True makes FastAPI serve index.html for any unmatched path,
    # which is what the React SPA router needs to handle client-side
    # routes (e.g. /step/3) without hitting the API.
    app.mount(
        "/",
        StaticFiles(directory=str(_FRONTEND_DIST), html=True),
        name="frontend",
    )
    logger.info("Serving frontend static files from %s", _FRONTEND_DIST)
else:
    logger.info(
        "Frontend dist not found at %s; running API only "
        "(use `npm run dev` from web/frontend for local UI)",
        _FRONTEND_DIST,
    )
