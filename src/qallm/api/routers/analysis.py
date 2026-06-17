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


def _round_code_metrics(sources: list[str]) -> dict:
    """Compute real code metrics for a round from its analysed sources.

    Uses Radon for maintainability index (mi, averaged across units),
    cyclomatic complexity (cc, summed), and lines of code (loc, summed). These
    are the metrics we can compute directly and honestly. Cognitive complexity
    (cs), code duplication (codu), and comment density (code) require SonarQube
    measures that are not retained per round, so they are reported as null
    rather than fabricated. Returns a dict with numeric values where available.
    """
    if not sources:
        return {"mi": None, "cc": None, "loc": None,
                "cs": None, "codu": None, "code": None}
    try:
        from radon.complexity import cc_visit
        from radon.metrics import mi_visit
        from radon.raw import analyze as raw_analyze
    except Exception:  # radon missing for some reason: report nothing rather than fake
        return {"mi": None, "cc": None, "loc": None,
                "cs": None, "codu": None, "code": None}

    mis: list[float] = []
    cc_total = 0
    loc_total = 0
    for src in sources:
        try:
            mis.append(float(mi_visit(src, True)))
        except Exception:
            pass
        try:
            cc_total += sum(b.complexity for b in cc_visit(src))
        except Exception:
            pass
        try:
            loc_total += raw_analyze(src).loc
        except Exception:
            pass
    return {
        "mi": round(sum(mis) / len(mis), 2) if mis else None,
        "cc": cc_total,
        "loc": loc_total,
        # Not computed here (need SonarQube measures); null, not zero.
        "cs": None, "codu": None, "code": None,
    }


@router.post("/api/session/{session_id}/confirm-findings")
async def confirm_findings(session_id: str):
    """Confirm or refute each static finding individually by execution.

    For each finding on a unit, a targeted test is generated and run to
    decide whether the finding reproduces (confirmed), does not (refuted),
    could not be tested (inconclusive), or is a finding type execution
    cannot judge such as complexity (not_execution_testable). Reuses the
    session's test-generation model and token tracker.

    This makes LLM calls, so it is an explicit POST action rather than
    something computed on every page load.
    """
    from qallm.verification.confirm_refute import FindingConfirmer
    from qallm.verification.extractor import extract_functions_from_source
    from qallm.analysis.gap_analysis import function_spans, _function_for_line

    state = get_state(session_id)
    orch: QALLMOrchestrator = state["orchestrator"]
    confirmer = FindingConfirmer(orch.testgen_llm, orch.tracker)

    analysed_units = state.get("analysed_units", {})
    if not analysed_units:
        return {"available": False, "verdicts": [],
                "reason": "Run analysis first so there are findings to confirm."}

    all_verdicts: list[dict] = []
    confirmed = refuted = inconclusive = not_testable = 0

    for name, analysed in analysed_units.items():
        findings = [asdict(f) for f in analysed.findings]
        if not findings:
            continue
        source = analysed.code_unit.source_code
        spans = function_spans(source)
        funcs = {f.name: f for f in extract_functions_from_source(source, name)}

        # Group findings by the function their line falls in, so each
        # function's findings are confirmed against that function's code.
        for fname, func in funcs.items():
            fn_findings = [
                f for f in findings
                if _function_for_line(spans, int(f.get("line", 0) or 0)) == fname
            ]
            if not fn_findings:
                continue
            report = confirmer.confirm_findings(
                func=func,
                findings=fn_findings,
                source_code=source,
                source_filename=name,
                source_origin=analysed.code_unit.original_path,
            )
            confirmed += report.confirmed
            refuted += report.refuted
            inconclusive += report.inconclusive
            not_testable += report.not_testable
            for v in report.verdicts:
                d = v.to_dict()
                d["file"] = name
                all_verdicts.append(d)

    denom = confirmed + refuted
    summary = {
        "confirmed": confirmed,
        "refuted": refuted,
        "inconclusive": inconclusive,
        "not_execution_testable": not_testable,
        "confirmation_rate": (confirmed / denom) if denom else None,
    }
    # Record on session state so the metrics export can include it.
    state["confirm_summary"] = summary
    return {
        "available": True,
        "verdicts": all_verdicts,
        "summary": summary,
    }


@router.post("/api/session/{session_id}/verify-fixes")
async def verify_fixes_endpoint(session_id: str, req: dict):
    """Prove that confirmed findings are fixed by the repair, via execution.

    Takes the confirmed findings (verdict dicts carrying a reproducing_test,
    as returned by /confirm-findings), re-runs each one's reproducing test
    against the repaired source for its file, and reports whether the defect
    is provably gone (verified_fixed), still present (not_fixed), or could
    not be re-tested (inconclusive).

    The confirmed findings are passed in from the client (which already has
    them from the confirm step) so no LLM calls are repeated; this endpoint
    is pure execution.
    """
    from qallm.verification.verified_fix import verify_fixes

    state = get_state(session_id)
    repaired_units = state.get("repaired_units", {})
    if not repaired_units:
        return {"available": False, "results": [],
                "reason": "No repaired code yet. Run repair first."}

    findings = req.get("findings") or []
    if not findings:
        return {"available": False, "results": [],
                "reason": "No confirmed findings provided to verify."}

    # Group the confirmed findings by file so each is re-run against the
    # repaired source for its own unit.
    by_file: dict[str, list[dict]] = {}
    for f in findings:
        by_file.setdefault(f.get("file") or "", []).append(f)

    all_results: list[dict] = []
    verified_fixed = not_fixed = inconclusive = 0
    for name, file_findings in by_file.items():
        repaired = repaired_units.get(name)
        if not repaired:
            # No repair for this file: its findings cannot be verified fixed.
            for f in file_findings:
                all_results.append({
                    **{k: f.get(k) for k in (
                        "finding_index", "tool", "type", "severity", "line",
                        "message", "rule_id", "function")},
                    "file": name,
                    "fix_verdict": "inconclusive",
                    "reason": "No repaired version of this file to test against.",
                })
                inconclusive += 1
            continue
        repaired_unit = repaired.repaired_code_unit
        report = verify_fixes(
            confirmed_findings=file_findings,
            repaired_source=repaired_unit.source_code,
            source_filename=name,
            source_origin=repaired_unit.original_path,
        )
        verified_fixed += report.verified_fixed
        not_fixed += report.not_fixed
        inconclusive += report.inconclusive
        for r in report.results:
            d = r.to_dict()
            d["file"] = name
            all_results.append(d)

    denom = verified_fixed + not_fixed
    summary = {
        "verified_fixed": verified_fixed,
        "not_fixed": not_fixed,
        "inconclusive": inconclusive,
        "verified_fix_rate": (verified_fixed / denom) if denom else None,
    }
    state["verify_summary"] = summary
    return {
        "available": True,
        "results": all_results,
        "summary": summary,
    }


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

    # Real code metrics for this round, computed from the analysed source via
    # Radon (MI, CC, LoC), not faked from severity buckets. Averaged/summed
    # across the analysed units. These feed the "paper metrics" panel honestly;
    # metrics that need SonarQube measures (cognitive complexity, duplication,
    # comment density) are left null when unavailable rather than shown as zero.
    metrics = _round_code_metrics(
        [state["analysed_units"][u.original_path.name].code_unit.source_code
         for u in state["units"]
         if u.original_path.name in selected_files
         and u.original_path.name in state["analysed_units"]]
    )

    summary = {
        "total": len(all_findings),
        "by_severity": {
            s: len([f for f in all_findings if f.severity == s])
            for s in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        },
        "metrics": metrics,
    }
    # Store a per-finding record so the re-analyse view can diff rounds (which
    # findings were resolved, introduced, or persist) AND expand each one to its
    # detail, the same as the baseline view. code_snippet is included so the
    # diff rows can show the offending code, matching the baseline finding rows.
    round_findings = [
        {"tool": f.tool, "type": f.type, "severity": f.severity,
         "file": f.file, "line": f.line, "rule_id": f.rule_id,
         "message": f.message, "code_snippet": f.code_snippet}
        for f in all_findings
    ]
    state["analysis_rounds"].append({
        "round": len(state["analysis_rounds"]), **summary,
        "findings": round_findings,
    })

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
        m = ar.get("metrics") or {}
        rounds_data.append({
            "round": i,
            "label": "Baseline" if i == 0 else f"Round {i}",
            # Real metrics computed from the round's source. null where a metric
            # is not available (e.g. SonarQube measures not retained per round),
            # rather than fabricated as zero.
            "cs": m.get("cs"),
            "mi": m.get("mi"),
            "codu": m.get("codu"),
            "code": m.get("code"),
            "loc": m.get("loc"),
            "cc": m.get("cc"),
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
        cm = curr.get("metrics") or {}
        bm = rounds[0].get("metrics") or {}

        def _delta(a, b):
            # Delta only when both ends are real numbers; else null.
            return (a - b) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None

        comparisons.append({
            "round": i,
            "vs_baseline": {
                "cs_delta": _delta(cm.get("cs"), bm.get("cs")),
                "mi_delta": _delta(cm.get("mi"), bm.get("mi")),
                "codu_delta": _delta(cm.get("codu"), bm.get("codu")),
                "code_delta": _delta(cm.get("code"), bm.get("code")),
                "loc_delta": _delta(cm.get("loc"), bm.get("loc")),
                "cc_delta": _delta(cm.get("cc"), bm.get("cc")),
                # Total findings delta is a real, separate signal worth keeping.
                "findings_delta": curr.get("total", 0) - rounds[0].get("total", 0),
            },
            "vs_previous": {
                "findings_delta": curr.get("total", 0) - prev.get("total", 0),
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


