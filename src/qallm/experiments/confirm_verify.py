"""Batch confirm/refute and verify-fixes from a session's persisted artefacts.

The web endpoints drive confirm/refute and verify-fixes from in-memory
session state. The batch runner has no such session: it constructs the
orchestrator directly and works from what each run persists to disk. This
module reconstructs the inputs those two steps need purely from the report
directory, so the batch path produces the same RQ2 (confirmation) and RQ3
(verified-fix) numbers the UI does, without depending on API session state.

What it reads from the report dir:
* Baseline (round 0) source and static findings, to confirm/refute each
  finding against the original code.
* The final accepted source per unit (the last lineage round), to re-run a
  confirmed finding's reproducing test against the repaired code.

These steps make LLM calls (the targeted-test generation in confirm/refute),
so the runner only invokes this when explicitly asked.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _baseline_dir(report_dir: str) -> str | None:
    """Resolve the round-0 lineage directory.

    The reporter writes round_{n:02d}, so the baseline is round_00, but an
    earlier convention used round_0. Looking only for round_0 (as this did)
    found nothing on real runs, so confirm/verify silently returned 0
    confirmed / 0 refuted. Try both names.
    """
    for name in ("round_00", "round_0"):
        candidate = os.path.join(report_dir, "lineage", name)
        if os.path.isdir(candidate):
            return candidate
    return None


def _baseline_units(report_dir: str) -> dict[str, dict]:
    """Map unit name -> {source, findings} from the round-0 (baseline) artefacts.

    Round 0 is the original code before any repair, the right basis for
    confirm/refute.
    """
    units: dict[str, dict] = {}
    base = _baseline_dir(report_dir)
    if base is None:
        return units
    for unit_seg in sorted(os.listdir(base)):
        unit_dir = os.path.join(base, unit_seg)
        if not os.path.isdir(unit_dir):
            continue
        source = _read_text(os.path.join(unit_dir, "source.py"))
        findings = _read_json(os.path.join(unit_dir, "static.json")) or []
        if source:
            units[unit_seg] = {"source": source, "findings": findings}
    return units


def _final_sources(report_dir: str) -> dict[str, str]:
    """Map unit name -> final accepted source (highest-numbered lineage round).

    The last accepted round is the repaired code, the basis for verify-fixes.
    """
    finals: dict[str, str] = {}
    lineage = os.path.join(report_dir, "lineage")
    if not os.path.isdir(lineage):
        return finals
    round_dirs = []
    for round_name in os.listdir(lineage):
        if not round_name.startswith("round_"):
            continue
        try:
            round_dirs.append((int(round_name.replace("round_", "")), round_name))
        except ValueError:
            continue
    for _, round_name in sorted(round_dirs):  # ascending: later overwrites earlier
        round_path = os.path.join(lineage, round_name)
        for unit_seg in os.listdir(round_path):
            unit_dir = os.path.join(round_path, unit_seg)
            source = _read_text(os.path.join(unit_dir, "source.py"))
            if source:
                finals[unit_seg] = source
    return finals


def confirm_and_verify_from_dir(report_dir: str, testgen_llm, tracker=None) -> dict:
    """Run confirm/refute (RQ2) and verify-fixes (RQ3) from disk artefacts.

    Returns {"confirm_summary": {...} | None, "verify_summary": {...} | None}
    matching the shapes the endpoints record on session state, so
    build_session_metrics can consume them unchanged. Summaries are None when
    there was nothing to do (no findings, or no repaired source).
    """
    from qallm.verification.confirm_refute import FindingConfirmer
    from qallm.verification.verified_fix import verify_fixes
    from qallm.verification.extractor import extract_functions_from_source
    from qallm.analysis.gap_analysis import function_spans, _function_for_line

    baseline = _baseline_units(report_dir)
    if not baseline:
        return {"confirm_summary": None, "verify_summary": None}

    confirmer = FindingConfirmer(testgen_llm, tracker)
    confirmed = refuted = inconclusive = not_testable = 0
    confirmed_verdicts: list[dict] = []

    for name, unit in baseline.items():
        findings = unit["findings"]
        if not findings:
            continue
        source = unit["source"]
        spans = function_spans(source)
        funcs = {f.name: f for f in extract_functions_from_source(source, name)}
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
                source_filename=name if name.endswith(".py") else f"{name}.py",
            )
            confirmed += report.confirmed
            refuted += report.refuted
            inconclusive += report.inconclusive
            not_testable += report.not_testable
            for v in report.verdicts:
                d = v.to_dict()
                d["file"] = name
                if d.get("verdict") == "confirmed":
                    confirmed_verdicts.append(d)

    denom = confirmed + refuted
    confirm_summary = {
        "confirmed": confirmed,
        "refuted": refuted,
        "inconclusive": inconclusive,
        "not_execution_testable": not_testable,
        "confirmation_rate": (confirmed / denom) if denom else None,
    }

    # Verify fixes: re-run each confirmed finding's reproducing test against
    # the final (repaired) source for its unit.
    verify_summary = None
    if confirmed_verdicts:
        finals = _final_sources(report_dir)
        by_file: dict[str, list[dict]] = {}
        for f in confirmed_verdicts:
            by_file.setdefault(f.get("file") or "", []).append(f)
        verified_fixed = not_fixed = vinconclusive = 0
        for name, file_findings in by_file.items():
            repaired_source = finals.get(name)
            if not repaired_source:
                vinconclusive += len(file_findings)
                continue
            report = verify_fixes(
                confirmed_findings=file_findings,
                repaired_source=repaired_source,
                source_filename=name if name.endswith(".py") else f"{name}.py",
            )
            verified_fixed += report.verified_fixed
            not_fixed += report.not_fixed
            vinconclusive += report.inconclusive
        vdenom = verified_fixed + not_fixed
        verify_summary = {
            "verified_fixed": verified_fixed,
            "not_fixed": not_fixed,
            "inconclusive": vinconclusive,
            "verified_fix_rate": (verified_fixed / vdenom) if vdenom else None,
        }

    return {"confirm_summary": confirm_summary, "verify_summary": verify_summary}
