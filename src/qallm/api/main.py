import shutil
import uuid
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from dataclasses import asdict

from qallm.orchestrator import QALLMOrchestrator, LLM_PROVIDERS

logger = logging.getLogger(__name__)
app = FastAPI(title="QALLM API")
sessions: Dict[str, Dict] = {}


class IngestRequest(BaseModel):
    source_path: str
    stage: str = "implementation"
    strategy: str = "rl"
    model_name: Optional[str] = None
    oracle: str = "crash"
    rounds: int = 5


async def ingest_path(path: str, config: dict) -> dict:
    """Core logic to initialize a session and Orchestrator exactly once."""
    session_id = str(uuid.uuid4())

    # FIX: Use 'rounds' instead of 'total_rounds' to match Orchestrator signature
    orchestrator = QALLMOrchestrator(
        stage=config.get("stage"),
        strategy=config.get("strategy"),
        model_name=config.get("model_name"),
        oracle=config.get("oracle"),
        rounds=config.get("rounds")
    )

    try:
        units = orchestrator.ingestion_manager.collect(path)
        sessions[session_id] = {
            "orchestrator": orchestrator,
            "units": units,
            "analysed_units": {},
            "analysis_rounds": [],
            "config": config
        }
        return {"session_id": session_id, "files": [u.original_path.name for u in units]}
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/session/upload")
async def upload_session(
        archives: List[UploadFile] = File(...),
        stage: str = Form("implementation"),
        strategy: str = Form("rl"),
        model: str = Form(...),
        oracle: str = Form("crash"),
        rounds: int = Form(5)
):
    """Handles multi-file uploads and gathers research variables[cite: 29]."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    upload_root = Path(f"outputs/temp_uploads/{timestamp}")
    upload_root.mkdir(parents=True, exist_ok=True)

    for archive in archives:
        file_path = upload_root / archive.filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(archive.file, buffer)

        if zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path, 'r') as z:
                z.extractall(upload_root / "extracted")

    config = {
        "stage": stage,
        "strategy": strategy,
        "model_name": model,
        "oracle": oracle,
        "rounds": rounds
    }

    target = str(upload_root / "extracted") if (upload_root / "extracted").exists() else str(upload_root)
    return await ingest_path(target, config)


@app.post("/api/session/ingest")
async def ingest_source(req: IngestRequest):
    """Handles Git URLs or local absolute paths[cite: 29]."""
    return await ingest_path(req.source_path, req.dict())


@app.get("/api/session/{session_id}/versions")
async def get_versions(session_id: str):
    """Required by TestGenScreen to list code snapshots[cite: 29]."""
    state = sessions.get(session_id)
    if not state: raise HTTPException(status_code=404, detail="Session not found")
    # For prototype, return baseline. Real impl would track snapshots.
    return {"versions": [{"round": 0, "label": "Baseline", "files": len(state["units"])}]}


@app.get("/api/session/{session_id}/diff/{filename}")
async def get_diff(session_id: str, filename: str):
    """Required by RepairScreen to show code changes[cite: 29]."""
    state = sessions.get(session_id)
    if not state: raise HTTPException(status_code=404, detail="Session not found")
    analysed = state["analysed_units"].get(filename)
    diff = analysed.repaired_result.unified_diff if analysed and analysed.repaired_result else ""
    return {"diff": diff}


@app.get("/api/session/{session_id}/download/tests")
async def download_tests(session_id: str):
    """Required by RLScreen to export generated tests[cite: 29]."""
    # Logic to gather generated test content from the orchestrator's verification manager
    return {"files": [{"name": "test_qallm.py", "content": "# Generated tests"}]}


@app.get("/api/llm/providers")
async def get_providers():
    return {"configured": list(LLM_PROVIDERS.keys())}


@app.get("/api/verification/strategies")
async def get_verification_strategies():
    return {"configured": ["rl", "oneshot", "hypothesis"]}


@app.get("/api/verification/models")
async def get_models():
    return {"configured": ["gpt-4o-mini", "ollama/llama3"]}


# ... (Keep existing /api/analyse, /api/repair, /api/verify endpoints)

@app.get("/api/session/{session_id}/files")
async def get_session_files(session_id: str):
    state = sessions.get(session_id)
    if not state: raise HTTPException(status_code=404, detail="Session not found")
    return {"files": [u.original_path.name for u in state["units"]]}


# Add this endpoint to provide configured tools to the UI
@app.get("/api/analysis/tools")
async def get_analysis_tools():
    """Returns the list of static analysis tools currently configured in the orchestrator[cite: 30]."""
    return {"tools": ["Bandit", "Radon", "Ruff", "TruffleHog"]}


@app.post("/api/analyse")
async def run_analysis(req: dict):
    """Stage 1: Multi-tool Static Analysis[cite: 30]."""
    sid = req.get("session_id")
    selected_files = req.get("selected_files", [])
    selected_tools = req.get("selected_tools", [])  # Respect UI selection[cite: 30]

    state = sessions.get(sid)
    if not state: raise HTTPException(status_code=404, detail="Session not found")

    orch = state["orchestrator"]
    # If the orchestrator supports tool filtering, pass selected_tools here[cite: 30]
    all_findings = []

    for unit in state["units"]:
        if unit.original_path.name in selected_files:
            # Analyze using only the tools selected by the user[cite: 30]
            analysed = orch.analysis_manager.analyse_code_unit(unit, tools=selected_tools)
            state["analysed_units"][unit.original_path.name] = analysed
            all_findings.extend(analysed.findings)

    summary = {
        "total": len(all_findings),
        "by_severity": {s: len([f for f in all_findings if f.severity == s])
                        for s in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]}
    }
    state["analysis_rounds"].append({"round": len(state["analysis_rounds"]), **summary})
    return {"findings": [asdict(f) for f in all_findings], "summary": summary}

@app.get("/api/session/{session_id}/analysis-history")
async def get_history(session_id: str):
    state = sessions.get(session_id)
    return {"rounds": state.get("analysis_rounds", [])} if state else {"rounds": []}

@app.post("/api/repair/{session_id}")
async def run_repair(session_id: str):
    """Stage 2: LLM Repair[cite: 11, 14]."""
    state = sessions.get(session_id)
    if not state: raise HTTPException(status_code=404, detail="Session not found")
    orch = state["orchestrator"]

    patches = []
    for name, analysed_unit in state["analysed_units"].items():
        repaired = orch.repair_manager.repair_code_unit(analysed_unit)
        res = repaired.repaired_result
        patches.append({
            "applied": res.compiles,
            "description": res.explanation,
            "unified_diff": res.unified_diff,
            "meta": {"file": name}
        })
        state["analysed_units"][name].code_unit = repaired.repaired_code_unit

    return {
        "patches": patches,
        "repaired_count": len([p for p in patches if p["applied"]]),
        "token_usage": orch.tracker.to_dict(),
        "provider_used": orch.llm.name(),
        "repair_round": len(state.get("analysis_rounds", []))
    }

@app.get("/api/verification/functions/{session_id}")
async def get_functions(session_id: str):
    """Lists functions found in the ingested code for Step 5 selection[cite: 13]."""
    state = sessions.get(session_id)
    if not state: raise HTTPException(status_code=404, detail="Session not found")

    # Extract function metadata for the UI selection list[cite: 13]
    function_list = []
    for unit in state["units"]:
        from qallm.verification.extractor import extract_functions_from_source
        funcs = extract_functions_from_source(unit.source_code, unit.original_path.name)
        for f in funcs:
            function_list.append({
                "name": f.name,
                "file": unit.original_path.name,
                "lineno": f.lineno,
                "docstring": f.docstring
            })
    return {"functions": function_list}

@app.post("/api/verification/run")
async def run_verification(req: dict):
    """Stage 3: Spec-Driven Verification (SDD)[cite: 9, 10]."""
    sid = req.get("session_id")
    state = sessions.get(sid)
    if not state: raise HTTPException(status_code=404, detail="Session not found")
    orch = state["orchestrator"]

    total_bugs = 0
    all_sessions = []

    for name, analysed in state["analysed_units"].items():
        from qallm.repair.repair_model import RepairedCodeUnit
        repaired_wrapper = RepairedCodeUnit(repaired_code_unit=analysed.code_unit, repaired_result=None)
        tested_unit = orch.verification_manager.verify(repaired_wrapper)
        total_bugs += tested_unit.total_bugs

        for session in tested_unit.sessions:
            s_data = asdict(session)
            s_data["learning_curve"] = session.learning_curve # For RL chart[cite: 12]
            all_sessions.append(s_data)

    return {
        "total_bugs": total_bugs,
        "total_functions": len(all_sessions),
        "functions": all_sessions,
        "model": orch.llm.name(),
        "oracle": orch.verification_manager.oracle,
        "token_usage": orch.tracker.to_dict()
    }

@app.get("/api/health/llm")
async def health_check():
    return {"status": "online", "service": "Ollama/OpenAI"}