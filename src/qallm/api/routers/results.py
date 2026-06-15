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
from fastapi.responses import PlainTextResponse

from qallm.api.core import (
    get_state,
    sessions,
)
from qallm.analysis.gap_analysis import compute_gap_rounds_from_dir
from qallm.metrics_export import (
    aggregate_sessions,
    build_session_metrics,
    to_csv,
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


def _extract_test_bodies(test_code: str | None) -> dict[str, str]:
    """Map each test function name to its exact source body.

    Parsing the generated test file with AST lets the UI show the precise
    method body for every test, so a passing test is self-evident from its
    body and a failing one can be read alongside its failure reason. Falls
    back to an empty map if the code does not parse.
    """
    if not test_code:
        return {}
    import ast

    bodies: dict[str, str] = {}
    try:
        tree = ast.parse(test_code)
    except SyntaxError:
        return {}
    lines = test_code.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("test"):
                continue
            start = node.lineno - 1
            end = getattr(node, "end_lineno", None)
            if end is None:
                continue
            bodies[node.name] = "\n".join(lines[start:end])
    return bodies


def _summarise_bug_detail(verification: list | None) -> list[dict]:
    """Extract per-function, per-test bug detail from a round's verification.

    The web UI shows aggregate counts ("4 bugs") but not *which* generated
    tests ran, their exact body, or why a failing one failed. This surfaces
    all of that: for each function verified in the round, the final round's
    executed tests with their pytest status (passed/failed/error/skipped),
    the exact test body (extracted from the generated test file), and the
    full failure reason. A failed test is a bug the generated tests caught
    by execution, the thing static analysis misses; success is self-evident
    from the presence of the test body.

    ``verification`` is the parsed verification.json: a list of session
    dicts (one per function), each with a ``rounds`` list whose last entry
    holds the ``execution`` with ``test_details`` and a ``generated_test``
    with the ``test_code``.
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
        generated = last.get("generated_test") or {}
        bodies = _extract_test_bodies(generated.get("test_code"))
        details = execution.get("test_details") or []

        def _bare_name(nodeid: str) -> str:
            # test_details names are pytest nodeids like
            # "test_generated.py::test_foo"; the body map is keyed by the
            # bare function name. Take the part after the last "::".
            return nodeid.rsplit("::", 1)[-1] if nodeid else ""

        tests = [
            {
                "name": d.get("name", "?"),
                "status": d.get("status", "?"),
                "message": d.get("message"),
                # The exact test method body; success is self-evident from it.
                "body": bodies.get(_bare_name(d.get("name", "")), ""),
            }
            for d in details
        ]
        functions.append({
            "function": session.get("function") or session.get("function_name", "?"),
            # The source of the function (code unit) under test. Shown
            # alongside the tests so a reviewer can read the test against
            # what it exercises; especially useful for passing tests.
            "source_code": session.get("source_code", ""),
            "passed": execution.get("passed", 0),
            "failed": execution.get("failed", 0),
            "errors": execution.get("errors", 0),
            "skipped": execution.get("skipped", 0),
            "total": execution.get("total", 0),
            # Tests dropped pre-execution for requesting undefined fixtures
            # (would have errored in setup); surfaced so the count is visible.
            "discarded": list(generated.get("discarded_tests") or []),
            "coverage_percent": execution.get("coverage_percent"),
            "execution_error": execution.get("execution_error"),
            # The full generated test file, for reference / download.
            "test_code": generated.get("test_code", ""),
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


@router.get("/api/session/{session_id}/gap")
def _resolve_report_dir(session_id: str) -> str | None:
    """The on-disk report dir for a session, from live state or the library."""
    state = sessions.get(session_id) or {}
    report_dir = state.get("report_dir")
    if report_dir and os.path.isdir(report_dir):
        return report_dir
    candidate = os.path.join(settings.QALLM_SESSIONS_DIR, session_id)
    return candidate if os.path.isdir(candidate) else None


def _compute_gap_rounds(report_dir: str) -> list[dict]:
    """Per-round gap dicts from a session's persisted round artefacts.

    Thin wrapper over the shared reader in qallm.analysis.gap_analysis, kept
    as a module-local name for the existing call sites in this router.
    """
    return compute_gap_rounds_from_dir(report_dir)


@router.get("/api/session/{session_id}/gap")
async def get_gap(session_id: str):
    """Static-vs-execution gap per round: which static findings execution
    confirmed, which it could not reproduce, and which execution-found bugs
    no static tool flagged (the verification gap).

    Reads each round's persisted source.py, static.json, and
    verification.json, so it works for live and historical sessions alike.
    """
    report_dir = _resolve_report_dir(session_id)
    if not report_dir:
        return {"available": False, "rounds": [],
                "reason": "No run artefacts yet. Run the pipeline first."}
    return {"available": True, "rounds": _compute_gap_rounds(report_dir)}


@router.get("/api/session/{session_id}/gap-confidence")
async def get_gap_confidence(session_id: str):
    """Mutation-based confidence for this session's verification-gap findings.

    For each execution-only (gap) function, mutates the function and runs its
    generated suite against each mutant; the kill rate becomes a confidence
    (high/medium/low/unknown). Returns the per-function scores and the
    distribution, so the UI can show how trustworthy the gap findings are, not
    just how many there are. Scores only the gap functions, so the cost is
    proportional to the number of findings.
    """
    report_dir = _resolve_report_dir(session_id)
    if not report_dir:
        return {"available": False,
                "reason": "No run artefacts yet. Run the pipeline first."}
    from qallm.experiments.gap_confidence import score_gap_confidence_from_dir
    # Gap functions = round-0 execution-only functions.
    gap_funcs: list[str] = []
    for r in _compute_gap_rounds(report_dir):
        if int(r.get("round", r.get("round_number", 0)) or 0) == 0:
            gap_funcs = list(r.get("execution_only_functions", []) or [])
            break
    if not gap_funcs:
        return {"available": True, "scored": 0, "per_function": {},
                "distribution": {"high": 0, "medium": 0, "low": 0, "unknown": 0},
                "reason": "No execution-only gap findings to score."}
    result = score_gap_confidence_from_dir(report_dir, gap_funcs)
    result["available"] = True
    return result


@router.get("/api/session/{session_id}/metrics")
async def get_session_metrics(session_id: str):
    """Thesis-ready metrics for one session: run metadata plus the
    verification-gap figures (always available), and the confirmation /
    verified-fix figures if those actions were run and recorded on the
    session state. Returns JSON; see /metrics.csv for the flat form.
    """
    report_dir = _resolve_report_dir(session_id)
    if not report_dir:
        return {"available": False,
                "reason": "No run artefacts yet. Run the pipeline first."}

    summary_path = os.path.join(report_dir, "summary.json")
    summary = None
    if os.path.isfile(summary_path):
        try:
            with open(summary_path, encoding="utf-8") as fh:
                summary = json.load(fh)
        except (OSError, json.JSONDecodeError):
            summary = None

    gap_rounds = _compute_gap_rounds(report_dir)
    # Confirmation / verified-fix summaries are recorded on the live session
    # state when those actions run; absent for historical sessions.
    state = sessions.get(session_id) or {}
    metrics = build_session_metrics(
        session_id=session_id,
        summary=summary,
        gap_rounds=gap_rounds,
        confirm_summary=state.get("confirm_summary"),
        verify_summary=state.get("verify_summary"),
    )
    return {"available": True, "metrics": metrics.to_dict()}


@router.get("/api/session/{session_id}/metrics.csv")
async def get_session_metrics_csv(session_id: str):
    """The single session's metrics as a one-row CSV (with header)."""
    report_dir = _resolve_report_dir(session_id)
    if not report_dir:
        return PlainTextResponse("", status_code=404)
    summary = None
    summary_path = os.path.join(report_dir, "summary.json")
    if os.path.isfile(summary_path):
        try:
            with open(summary_path, encoding="utf-8") as fh:
                summary = json.load(fh)
        except (OSError, json.JSONDecodeError):
            summary = None
    state = sessions.get(session_id) or {}
    metrics = build_session_metrics(
        session_id, summary, _compute_gap_rounds(report_dir),
        confirm_summary=state.get("confirm_summary"),
        verify_summary=state.get("verify_summary"),
    )
    csv_text = to_csv([metrics])
    return PlainTextResponse(csv_text, media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="qallm_metrics_{session_id}.csv"',
    })


@router.get("/api/metrics/aggregate")
async def get_aggregate_metrics():
    """Cross-session roll-up over every persisted session in the library.

    Rates are recomputed from summed counts (count-weighted), not averaged,
    so larger sessions weigh proportionally. Confirmation / verified-fix
    counts come from live state when present.
    """
    base = settings.QALLM_SESSIONS_DIR
    if not os.path.isdir(base):
        return {"available": False, "reason": "No sessions directory yet."}

    metrics_list = []
    for sid in sorted(os.listdir(base)):
        sdir = os.path.join(base, sid)
        if not os.path.isdir(sdir):
            continue
        summary = None
        summary_path = os.path.join(sdir, "summary.json")
        if os.path.isfile(summary_path):
            try:
                with open(summary_path, encoding="utf-8") as fh:
                    summary = json.load(fh)
            except (OSError, json.JSONDecodeError):
                summary = None
        gap_rounds = _compute_gap_rounds(sdir)
        if not gap_rounds and summary is None:
            continue
        state = sessions.get(sid) or {}
        metrics_list.append(build_session_metrics(
            sid, summary, gap_rounds,
            confirm_summary=state.get("confirm_summary"),
            verify_summary=state.get("verify_summary"),
        ))

    agg = aggregate_sessions(metrics_list)
    return {"available": True, "aggregate": agg.to_dict()}


@router.get("/api/health")
async def health():
    return {
        "status": "online",
        "openai": bool(settings.OPENAI_API_KEY),
        "anthropic": bool(settings.ANTHROPIC_API_KEY),
        "sessions": len(sessions),
    }

