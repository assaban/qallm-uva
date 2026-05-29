"""API router: analysis endpoints.

Split from the former monolithic api/main.py. Shares the app's session
store and helpers via qallm.api.core. Behaviour is unchanged; only the
file boundary moved.
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter

from qallm.api.core import (
    get_state,
)
from qallm.orchestrator import QALLMOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/analyse")
async def run_analysis(req: dict):
    """Run static analysis on the session's code units.

    Same endpoint serves both the initial Step 2 ("Analyse") and the
    Step 4 ("Re-analyse") call after repair. The endpoint picks the
    *latest* source for each unit: if a repair has run and produced a
    repaired variant, that's analysed; otherwise the original is.

    This is the right contract because analysis is always "what does
    the current state of this code look like to a static tool?", and
    the current state moves forward as repair lands. Without this,
    re-analyse would silently report the original code's findings,
    making the methodology claim ("repair improves quality") invisible
    in the UI.
    """
    sid = req.get("session_id", "")
    selected_files = req.get("selected_files", [])

    state = get_state(sid)
    orch: QALLMOrchestrator = state["orchestrator"]

    all_findings = []
    repaired_units = state.get("repaired_units", {})
    used_repaired = 0
    used_original = 0
    for unit in state["units"]:
        name = unit.original_path.name
        if name not in selected_files:
            continue

        # If a repaired variant of this unit exists from an earlier step,
        # analyse it instead of the original. Otherwise fall back. We
        # require ``compiles=True`` so we don't analyse a syntactically
        # broken repair attempt.
        repaired = repaired_units.get(name)
        if (repaired
                and repaired.repaired_result
                and repaired.repaired_result.compiles):
            target_unit = repaired.repaired_code_unit
            used_repaired += 1
        else:
            target_unit = unit
            used_original += 1

        analysed = orch.analysis_manager.analyse_code_unit(target_unit)
        state["analysed_units"][name] = analysed
        all_findings.extend(analysed.findings)

    logger.info(
        "Analysis run on session %s: %d unit(s) using repaired source, "
        "%d using original.",
        sid, used_repaired, used_original,
    )

    summary = {
        "total": len(all_findings),
        "by_severity": {
            s: len([f for f in all_findings if f.severity == s])
            for s in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        },
    }
    state["analysis_rounds"].append({"round": len(state["analysis_rounds"]), **summary})

    return {"findings": [asdict(f) for f in all_findings], "summary": summary}


@router.get("/api/session/{session_id}/analysis-history")
async def get_analysis_history(session_id: str):
    state = get_state(session_id)
    return {"rounds": state.get("analysis_rounds", [])}


@router.get("/api/session/{session_id}/files")
async def get_session_files(session_id: str):
    state = get_state(session_id)
    return {"files": [u.original_path.name for u in state["units"]]}


@router.get("/api/session/{session_id}/paper-metrics-history")
async def get_paper_metrics_history(session_id: str):
    """Metrics history across analysis rounds for the ReanalyseScreen table."""
    state = get_state(session_id)
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


@router.get("/api/session/{session_id}/comparisons")
async def get_comparisons(session_id: str):
    """Computes deltas between analysis rounds."""
    state = get_state(session_id)
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


@router.get("/api/session/{session_id}/rounds")
async def get_rounds(session_id: str):
    """Lists all repair/analysis rounds for the round selector."""
    state = get_state(session_id)
    rounds = []
    rounds.append({"round": 0, "label": "Baseline", "files": len(state["units"]), "has_findings": True, "has_tests": False})
    for i, ar in enumerate(state.get("analysis_rounds", []), 1):
        rounds.append({"round": i, "label": f"Round {i}", "files": len(state["units"]), "has_findings": True, "has_tests": False})
    if state.get("verification_sessions"):
        rounds[-1]["has_tests"] = True
    return {"rounds": rounds}


