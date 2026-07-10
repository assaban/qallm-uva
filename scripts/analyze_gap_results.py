#!/usr/bin/env python3
"""Analyze a gap-experiment run directory from its results.jsonl.

Recomputes every reported number directly from the per-session rows, which
are the authoritative record (the shipped aggregate.json of runs made before
the aggregate fixes carried a degenerate gap rate and a lost RQ2 split; see
tests/test_aggregate_gap_rate.py). Produces:

- analysis.json: all computed numbers, machine-readable
- analysis.md: the same numbers as a readable summary

Reported, per the thesis conventions:
- RQ1 count-weighted gap rate with a session-resample bootstrap 95% CI,
  plus project-weighted (macro) rates, the per-project distribution, and a
  dominant-project sensitivity check (corpora are skewed; one repository can
  carry a fifth of the denominator).
- RQ2 as counts, not a rate: confirmed reliability defects (each with a
  persisted reproducing test), inconclusive static findings, refuted.
  Refutation is structurally near-impossible by design (MD-006), so a
  confirmed/(confirmed+refuted) ratio is not a meaningful statistic.
- RQ3 verified-fix rate with bootstrap CI.
- Mutation-confidence distribution over gap findings when present.

Usage:
    python scripts/analyze_gap_results.py --run runs/e2_final
    python scripts/analyze_gap_results.py --run runs/e2_final --project-depth 2
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path


def _read_rows(path: Path) -> tuple[list[dict], int]:
    rows, corrupt = [], 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                corrupt += 1
    return rows, corrupt


def _bootstrap_ratio(pairs: list[tuple[int, int]], n_boot: int = 10000,
                     seed: int = 42) -> dict:
    """Percentile bootstrap CI for a pooled ratio, resampling sessions."""
    rng = random.Random(seed)
    num = sum(a for a, _ in pairs)
    den = sum(b for _, b in pairs)
    point = (num / den) if den else None
    if point is None:
        return {"point": None, "ci_low": None, "ci_high": None,
                "n_sessions": len(pairs), "n_boot": n_boot}
    stats = []
    for _ in range(n_boot):
        smp = rng.choices(pairs, k=len(pairs))
        d = sum(b for _, b in smp)
        stats.append((sum(a for a, _ in smp) / d) if d else 0.0)
    stats.sort()
    # Full precision here; presentation rounding happens once, at format
    # time, so a display percentage never rounds an already-rounded value.
    return {
        "point": point,
        "ci_low": stats[int(0.025 * n_boot)],
        "ci_high": stats[int(0.975 * n_boot)],
        "n_sessions": len(pairs),
        "n_boot": n_boot,
        "method": "bootstrap_percentile_session_resample",
    }


def analyze(run_dir: Path, project_depth: int = 1) -> dict:
    rows, corrupt = _read_rows(run_dir / "results.jsonl")
    ok = [r for r in rows if not r.get("error")]
    errored = len(rows) - len(ok)
    metrics = [r["metrics"] for r in ok]

    def total(key: str) -> int:
        return sum(int(m.get(key) or 0) for m in metrics)

    fv = total("functions_verified")
    gaps = total("execution_only_bugs")

    gap_pairs = [(int(m.get("execution_only_bugs") or 0),
                  int(m.get("functions_verified") or 0)) for m in metrics]
    fix_pairs = [(int(m.get("verified_fixed") or 0),
                  int(m.get("verified_fixed") or 0)
                  + int(m.get("not_fixed") or 0)) for m in metrics]

    # Per-project roll-up. The project is a path segment relative to the
    # dataset root; depth 1 means the first segment (the repository).
    per_project: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in ok:
        parts = Path(r.get("input", "")).parts
        # input paths look like datasets/<corpus>/<project>/...; take the
        # segment(s) after the corpus directory when present.
        seg = "/".join(parts[2:2 + project_depth]) if len(parts) > 2 else "?"
        per_project[seg][0] += int(r["metrics"].get("execution_only_bugs") or 0)
        per_project[seg][1] += int(r["metrics"].get("functions_verified") or 0)

    proj_rates = {p: (g / f) for p, (g, f) in per_project.items() if f >= 5}
    dominant = max(per_project.items(), key=lambda kv: kv[1][1]) if per_project else None
    sens = None
    if dominant and fv:
        dg, dfv = dominant[1]
        rest_fv = fv - dfv
        sens = {
            "project": dominant[0],
            "functions_verified": dfv,
            "share_of_denominator": round(dfv / fv, 4),
            "gap_rate_within": round(dg / dfv, 4) if dfv else None,
            "gap_rate_excluding": round((gaps - dg) / rest_fv, 4) if rest_fv else None,
        }

    confidence = defaultdict(int)
    scored = 0
    for r in ok:
        gc = r.get("gap_confidence") or {}
        for k, v in (gc.get("distribution") or {}).items():
            confidence[k] += int(v or 0)
        scored += int(gc.get("scored") or 0)

    rates_sorted = sorted(proj_rates.values())
    n = len(rates_sorted)
    result = {
        "run_dir": str(run_dir),
        "sessions": {"total": len(rows), "ok": len(ok), "errored": errored,
                     "corrupt_lines": corrupt},
        "rq1": {
            "functions_verified": fv,
            "execution_only_defects": gaps,
            "gap_rate_count_weighted": _bootstrap_ratio(gap_pairs),
            "gap_rate_project_weighted": {
                "min_functions_per_project": 5,
                "n_projects": n,
                "macro_average": round(statistics.mean(rates_sorted), 4) if n else None,
                "median": round(statistics.median(rates_sorted), 4) if n else None,
                "iqr": [round(rates_sorted[n // 4], 4),
                        round(rates_sorted[(3 * n) // 4], 4)] if n >= 4 else None,
                "projects_with_zero_gaps": sum(1 for x in rates_sorted if x == 0),
            },
            "dominant_project_sensitivity": sens,
            "not_execution_testable": total("not_execution_testable"),
            "incoherent_oracles_dropped": total("incoherent_oracles_dropped"),
        },
        "rq2_counts": {
            "confirmed_total": total("confirmed"),
            "confirmed_static": total("confirmed_static"),
            "confirmed_reliability_gap": total("confirmed_reliability_gap"),
            "refuted": total("refuted"),
            "inconclusive_static": total("inconclusive"),
            "note": ("Refutation is structurally near-impossible by design "
                     "(MD-006); report counts, not a confirmation rate."),
        },
        "rq3": {
            "verified_fixed": total("verified_fixed"),
            "fix_denominator": total("verified_fixed") + total("not_fixed"),
            "verified_fix_rate": _bootstrap_ratio(fix_pairs),
        },
        "gap_confidence": {"scored": scored, "distribution": dict(confidence)},
        "static_findings_total": total("static_findings"),
        "units_analyzed": total("units_analyzed"),
        "cost_usd": round(sum(float(m.get("cost_usd") or 0.0) for m in metrics), 4),
    }
    return result


def to_markdown(a: dict) -> str:
    rq1, rq2, rq3 = a["rq1"], a["rq2_counts"], a["rq3"]
    cw = rq1["gap_rate_count_weighted"]
    pw = rq1["gap_rate_project_weighted"]
    lines = [
        f"# Gap-run analysis: {a['run_dir']}",
        "",
        f"Sessions: {a['sessions']['ok']} analyzed, "
        f"{a['sessions']['errored']} errored, "
        f"{a['sessions']['corrupt_lines']} corrupt lines skipped.",
        "",
        "## RQ1: verification gap",
        f"- Count-weighted: {rq1['execution_only_defects']} execution-only "
        f"defects over {rq1['functions_verified']} verified functions = "
        f"{cw['point']:.1%} (95% CI [{cw['ci_low']:.1%}, {cw['ci_high']:.1%}], "
        f"session-resample bootstrap).",
        f"- Project-weighted (projects with >= {pw['min_functions_per_project']} "
        f"verified functions, n = {pw['n_projects']}): macro average "
        f"{pw['macro_average']:.1%}, median {pw['median']:.1%}, "
        f"IQR [{pw['iqr'][0]:.1%}, {pw['iqr'][1]:.1%}]; "
        f"{pw['projects_with_zero_gaps']} projects show zero gaps.",
    ]
    sens = rq1.get("dominant_project_sensitivity")
    if sens:
        lines.append(
            f"- Dominance check: `{sens['project']}` alone contributes "
            f"{sens['share_of_denominator']:.0%} of the denominator at a "
            f"{sens['gap_rate_within']:.1%} gap rate; excluding it, the "
            f"count-weighted rate is {sens['gap_rate_excluding']:.1%}.")
    lines += [
        "",
        "## RQ2: confirmation, reported as counts",
        f"- Confirmed reliability defects (each with a persisted reproducing "
        f"test): {rq2['confirmed_reliability_gap']}.",
        f"- Static findings: {rq2['confirmed_static']} confirmed, "
        f"{rq2['refuted']} refuted, {rq2['inconclusive_static']} inconclusive "
        f"(security findings are inconclusive by design).",
        "",
        "## RQ3: verified fixes",
        f"- {rq3['verified_fixed']}/{rq3['fix_denominator']} = "
        f"{rq3['verified_fix_rate']['point']:.1%} "
        f"(95% CI [{rq3['verified_fix_rate']['ci_low']:.1%}, "
        f"{rq3['verified_fix_rate']['ci_high']:.1%}]).",
        "",
        "## Oracle confidence over gap findings",
        f"- Scored: {a['gap_confidence']['scored']}; distribution: "
        f"{a['gap_confidence']['distribution']}.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, help="Run directory with results.jsonl")
    ap.add_argument("--project-depth", type=int, default=1,
                    help="Path segments after the corpus dir that identify a project.")
    args = ap.parse_args()
    run_dir = Path(args.run)
    result = analyze(run_dir, project_depth=args.project_depth)
    (run_dir / "analysis.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    (run_dir / "analysis.md").write_text(to_markdown(result), encoding="utf-8")
    print(to_markdown(result))


if __name__ == "__main__":
    main()
