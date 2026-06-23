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


def _module_name_from_findings(findings: list[dict]) -> str | None:
    """The source module name the reproducing tests import from.

    Generated tests import the function under test with a line like
    ``from source_reliability_gap_c0 import f``. The source must be written
    under that exact name or the test cannot import it. Recover the name from
    the first reproducing test that has an import, so verify-fixes does not
    depend on the unit-segment name matching the import.
    """
    import re
    for f in findings:
        code = f.get("reproducing_test") or ""
        m = re.search(r"(?m)^\s*from\s+(source_\w+)\s+import\b", code)
        if m:
            return m.group(1)
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


def _reliability_confirmations(report_dir: str, gap_rounds: list[dict]) -> list[dict]:
    """Confirmed reliability defects, from the execution-only (gap) defects.

    The static analysers never emit RELIABILITY findings: they flag security,
    complexity, and maintainability. So the static-finding confirmation path can
    only ever speak to security, which is inconclusive by design, and the
    reliability defects that are the heart of the verification gap have no static
    finding for that path to adjudicate.

    A gap defect is, however, already a confirmed reliability defect by
    construction: it is an execution-only defect, meaning a generated correctness
    test failed against the original (round-0) code. That failing test is the
    reproduction. This helper recovers, for each round-0 execution-only function,
    its round-0 test as the ``reproducing_test`` and records a confirmed
    RELIABILITY verdict, so RQ2 has a real confirmation count and RQ3 can re-run
    those tests against the repaired code (a pass means the defect is fixed).

    Read-only. It reads the round-0 ``tests/`` artefacts the reporter persists.
    """
    base = _baseline_dir(report_dir)
    if base is None:
        return []
    # Round-0 execution-only functions per unit are listed in the round-0 gap
    # report; fall back to an empty list when absent.
    gap_funcs: list[str] = []
    for r in gap_rounds:
        if int(r.get("round", r.get("round_number", 0)) or 0) == 0:
            gap_funcs = list(r.get("execution_only_functions", []) or [])
            break
    if not gap_funcs:
        return []

    confirmations: list[dict] = []
    for unit_seg in sorted(os.listdir(base)):
        unit_dir = os.path.join(base, unit_seg)
        tests_dir = os.path.join(unit_dir, "tests")
        if not os.path.isdir(tests_dir):
            continue
        for fname in gap_funcs:
            test_path = os.path.join(tests_dir, f"test_{fname}.py")
            test_code = _read_text(test_path)
            if not test_code.strip():
                continue
            confirmations.append({
                "finding_index": -1,
                "tool": "execution",
                "type": "RELIABILITY",
                "severity": "?",
                "line": 0,
                "message": (
                    "Execution-only defect: a correctness test failed against "
                    "the original code, reproducing a reliability defect that "
                    "static analysis did not flag."
                ),
                "rule_id": "gap.reliability",
                "function": fname,
                "verdict": "confirmed",
                "reason": (
                    "The generated correctness test failed on the baseline "
                    "source, demonstrating the defect."
                ),
                "reproducing_test": test_code,
                "file": unit_seg,
            })
    return confirmations


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


def confirm_and_verify_from_dir(report_dir: str, testgen_llm, tracker=None,
                                gap_rounds: list[dict] | None = None) -> dict:
    """Run confirm/refute (RQ2) and verify-fixes (RQ3) from disk artefacts.

    Returns {"confirm_summary": {...} | None, "verify_summary": {...} | None}
    matching the shapes the endpoints record on session state, so
    build_session_metrics can consume them unchanged. Summaries are None when
    there was nothing to do (no findings, or no repaired source).

    RQ2 has two confirmation sources, kept distinct in the summary:
    static-finding confirmation (security findings, which are inconclusive by
    design) and reliability confirmation derived from the execution-only gap
    defects (see _reliability_confirmations). The latter is what gives RQ2 a
    non-trivial confirmation count on this corpus, because static analysis emits
    no reliability findings.
    """
    from qallm.verification.confirm_refute import FindingConfirmer
    from qallm.verification.verified_fix import verify_fixes
    from qallm.verification.extractor import extract_functions_from_source
    from qallm.analysis.gap_analysis import function_spans, _function_for_line

    baseline = _baseline_units(report_dir)
    if not baseline:
        logger.info("Confirm/verify: no baseline units under %s.", report_dir)
        return {"confirm_summary": None, "verify_summary": None}

    confirmer = FindingConfirmer(testgen_llm, tracker)
    confirmed = refuted = inconclusive = not_testable = 0
    confirmed_verdicts: list[dict] = []

    total_findings = sum(len(u["findings"]) for u in baseline.values())
    units_with_findings = sum(1 for u in baseline.values() if u["findings"])
    logger.info(
        "Confirm/verify: %d baseline unit(s), %d with findings, %d finding(s) total.",
        len(baseline), units_with_findings, total_findings,
    )

    for name, unit in baseline.items():
        findings = unit["findings"]
        if not findings:
            continue
        source = unit["source"]
        spans = function_spans(source)
        funcs = {f.name: f for f in extract_functions_from_source(source, name)}
        mapped = 0
        for fname, func in funcs.items():
            fn_findings = [
                f for f in findings
                if _function_for_line(spans, int(f.get("line", 0) or 0)) == fname
            ]
            if not fn_findings:
                continue
            mapped += len(fn_findings)
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
        if findings and mapped == 0:
            # Findings exist but none mapped to a function: usually the finding
            # line falls outside every function span (module-level finding) or
            # the line is 0/missing. Surfaced so it is diagnosable, not silent.
            logger.info(
                "Confirm/verify: %s has %d finding(s) but none mapped to a "
                "function (lines: %s; spans: %s).",
                name, len(findings),
                [f.get("line") for f in findings],
                [(s.name, s.start, s.end) for s in spans],
            )

    # Reliability confirmations from the execution-only gap defects. These are
    # confirmed by construction (a correctness test failed on the baseline), so
    # they add to the confirmed count and carry a reproducing test for RQ3.
    rel_confirmations = _reliability_confirmations(report_dir, gap_rounds or [])
    reliability_confirmed = len(rel_confirmations)
    confirmed_verdicts.extend(rel_confirmations)
    confirmed_total = confirmed + reliability_confirmed
    confirm_denom = confirmed_total + refuted
    confirm_summary = {
        "confirmed": confirmed_total,
        "confirmed_static": confirmed,
        "confirmed_reliability_gap": reliability_confirmed,
        "refuted": refuted,
        "inconclusive": inconclusive,
        "not_execution_testable": not_testable,
        "confirmation_rate": (confirmed_total / confirm_denom) if confirm_denom else None,
    }
    logger.info(
        "Confirm/verify verdicts: confirmed=%d (static=%d, reliability_gap=%d) "
        "refuted=%d inconclusive=%d not_execution_testable=%d",
        confirmed_total, confirmed, reliability_confirmed, refuted,
        inconclusive, not_testable,
    )

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
            # The reproducing tests import the source under a specific module
            # name (for example source_reliability_gap_c0); the repaired source
            # must be written under that name or the test cannot import it and
            # the fix verdict is spuriously inconclusive. Derive it from the
            # tests rather than the unit segment name.
            derived = _module_name_from_findings(file_findings)
            source_filename = (
                f"{derived}.py" if derived
                else (name if name.endswith(".py") else f"{name}.py")
            )
            report = verify_fixes(
                confirmed_findings=file_findings,
                repaired_source=repaired_source,
                source_filename=source_filename,
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
