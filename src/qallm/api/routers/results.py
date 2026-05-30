"""API router: results endpoints.

Split from the former monolithic api/main.py. Shares the app's session
store and helpers via qallm.api.core. Behaviour is unchanged; only the
file boundary moved.
"""

from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter

from qallm.api.core import (
    get_state,
    sessions,
)
from qallm.config import settings
from qallm.orchestrator import QALLMOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/session/{session_id}/stats")
async def get_stats(session_id: str):
    state = get_state(session_id)
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


def _summarise_bug_detail(verification: list | None) -> list[dict]:
    """Extract per-function, per-test bug detail from a round's verification.

    The web UI shows aggregate counts ("4 bugs") but not *which* generated
    tests failed or why. This surfaces that: for each function verified in
    the round, the final round's executed tests with their pytest status
    (passed/failed/error/skipped) and the failure message. A failed test is
    a bug the generated tests caught by execution, the thing static analysis
    misses.

    ``verification`` is the parsed verification.json: a list of session
    dicts (one per function), each with a ``rounds`` list whose last entry
    holds the ``execution`` with ``test_details``.
    """
    if not verification:
        return []
    functions: list[dict] = []
    for session in verification:
        rounds = session.get("rounds") or []
        if not rounds:
            continue
        last = rounds[-1]
        execution = last.get("execution") or {}
        details = execution.get("test_details") or []
        tests = [
            {
                "name": d.get("name", "?"),
                "status": d.get("status", "?"),
                "message": d.get("message"),
            }
            for d in details
        ]
        functions.append({
            "function": session.get("function") or session.get("function_name", "?"),
            "passed": execution.get("passed", 0),
            "failed": execution.get("failed", 0),
            "errors": execution.get("errors", 0),
            "skipped": execution.get("skipped", 0),
            "total": execution.get("total", 0),
            "coverage_percent": execution.get("coverage_percent"),
            "execution_error": execution.get("execution_error"),
            # The bugs: tests that ran and failed (not errored).
            "bug_tests": [t for t in tests if t["status"] == "failed"],
            "all_tests": tests,
        })
    return functions


@router.get("/api/session/{session_id}/improvement")
async def get_improvement(session_id: str):
    """Per-round, per-unit improvement audit for the observability view.

    Reads the artefacts the orchestrator wrote during the run (improvement
    deltas, profile verdicts, transcripts) from the report directory, and
    returns them in a UI-friendly shape: a list of rounds, each with the
    units processed, the per-indicator deltas, the accept/abandon outcome,
    and the LLM calls (prompts + responses) made for that unit that round.

    This is the data behind "can we see, per round and per method, which
    findings were tracked and improved, and what we asked the model".
    """

    # Soft lookup: a historical session opened from the library is not a
    # live in-memory session, so get_state (which 404s) is wrong here. Read
    # the in-memory state if present, otherwise fall through to disk.
    state = sessions.get(session_id) or {}
    report_dir = state.get("report_dir")
    # Fall back to the on-disk session directory for historical sessions
    # that are not live in this process's memory (e.g. opened from the
    # session library). The session id is the reporter run-id, which is the
    # directory name under QALLM_SESSIONS_DIR.
    if not report_dir or not os.path.isdir(report_dir):
        candidate = os.path.join(settings.QALLM_SESSIONS_DIR, session_id)
        if os.path.isdir(candidate):
            report_dir = candidate
    if not report_dir or not os.path.isdir(report_dir):
        return {"available": False, "rounds": [],
                "reason": "No run artefacts yet. Run the pipeline first."}

    def _read_json(path: str):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None

    rounds: dict[int, dict] = {}
    for bucket in ("lineage", "abandoned"):
        bucket_dir = os.path.join(report_dir, bucket)
        if not os.path.isdir(bucket_dir):
            continue
        for round_name in sorted(os.listdir(bucket_dir)):
            round_path = os.path.join(bucket_dir, round_name)
            if not os.path.isdir(round_path):
                continue
            try:
                round_no = int(round_name.replace("round_", ""))
            except ValueError:
                continue
            for unit_seg in sorted(os.listdir(round_path)):
                unit_dir = os.path.join(round_path, unit_seg)
                if not os.path.isdir(unit_dir):
                    continue
                improvement = _read_json(os.path.join(unit_dir, "improvement.json"))
                profile = _read_json(os.path.join(unit_dir, "profile.json"))
                judge = _read_json(os.path.join(unit_dir, "judge.json"))
                transcript = _read_json(os.path.join(unit_dir, "transcript.json")) or []
                verification = _read_json(os.path.join(unit_dir, "verification.json"))
                unit_entry = {
                    "unit_id": unit_seg,
                    "bucket": bucket,
                    "accepted": bucket == "lineage" and round_no > 0,
                    "is_baseline": round_no == 0,
                    "improvement": improvement,
                    "profile": profile,
                    "judge": judge,
                    "llm_calls": transcript,
                    "bug_detail": _summarise_bug_detail(verification),
                }
                r = rounds.setdefault(round_no, {"round": round_no, "units": []})
                r["units"].append(unit_entry)

    ordered = [rounds[k] for k in sorted(rounds)]
    return {"available": True, "rounds": ordered}


@router.get("/api/session/{session_id}/download/tests")
async def download_tests(session_id: str):
    state = get_state(session_id)
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


@router.get("/api/health")
async def health():
    return {
        "status": "online",
        "openai": bool(settings.OPENAI_API_KEY),
        "anthropic": bool(settings.ANTHROPIC_API_KEY),
        "sessions": len(sessions),
    }

