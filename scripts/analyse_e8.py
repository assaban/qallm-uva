#!/usr/bin/env python3
"""
analyse-e8.py  (v2, matched to the real results.json schema)

Turns the arms produced by run-e8-oracle-across-models.sh into the six numbers
per row that Table~\\ref{tab:multimodel} needs.

v1 guessed at field names. This version reads the schema actually written by
src/qallm/experiments/humaneval_metrics.py, whose ProblemResult carries:

    task_id, strategy, model, bug_detected, repair_successful, rounds_run,
    total_bugs_reported, final_coverage, cost_usd, elapsed_seconds, error

Records with a non-null `error` are excluded from every rate, which is the same
convention AggregateResult uses, so a strategy is not penalised for an
infrastructure failure unrelated to its quality.

Usage:
    python3 analyse-e8.py --root runs/e8_oracle_x_model --prefix bench
    python3 analyse-e8.py --root runs/e8_oracle_x_model --prefix bench --latex
    python3 analyse-e8.py --root runs/e8_oracle_x_model --prefix bench --out e8.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

DETECT_FIELD = "bug_detected"
REPAIR_FIELD = "repair_successful"
ID_FIELD = "task_id"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_arm(arm_dir: Path, model_filter: str | None = None) -> tuple[dict, dict, dict]:
    """Return (detected, repaired, meta) keyed by task_id for one arm.

    An arm may contain more than one model if it was run with a comma-separated
    --models list, so the model is filtered here rather than assumed.
    """
    detected: dict[str, bool] = {}
    repaired: dict[str, bool] = {}
    cost = 0.0
    errored = 0
    seen_models: set[str] = set()

    files = sorted(arm_dir.rglob("results.json"))
    if not files:
        raise FileNotFoundError(f"no results.json under {arm_dir}")

    for path in files:
        blob = json.loads(path.read_text())
        recs = blob if isinstance(blob, list) else blob.get("results", blob.get("problems", []))
        if not isinstance(recs, list):
            continue
        for r in recs:
            if not isinstance(r, dict) or ID_FIELD not in r:
                continue
            m = r.get("model", "")
            seen_models.add(m)
            if model_filter and model_filter not in m:
                continue
            cost += float(r.get("cost_usd") or 0.0)
            if r.get("error"):
                errored += 1
                continue          # excluded from rates, counted for honesty
            tid = str(r[ID_FIELD])
            detected[tid] = bool(r.get(DETECT_FIELD))
            repaired[tid] = bool(r.get(REPAIR_FIELD))

    if not detected:
        raise ValueError(
            f"{arm_dir}: parsed {len(files)} results.json but no usable records"
            + (f" for model matching {model_filter!r}" if model_filter else "")
            + f". Models present: {sorted(seen_models) or 'none'}"
        )
    return detected, repaired, {"cost_usd": cost, "errored": errored,
                                "models_present": sorted(seen_models)}


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def mcnemar_exact(a: dict[str, bool], b: dict[str, bool]) -> dict:
    """Two-sided exact McNemar on the paired discordant outcomes.

    Under the null the discordant pairs split like a fair coin, so this is a
    two-sided binomial test on b of b+c at p=0.5. Exact rather than chi-square
    because the discordant counts here are small enough that the approximation
    is not safe.
    """
    shared = sorted(set(a) & set(b))
    n_b = sum(1 for k in shared if a[k] and not b[k])
    n_c = sum(1 for k in shared if b[k] and not a[k])
    n = n_b + n_c
    if n == 0:
        p = 1.0
    else:
        lo = min(n_b, n_c)
        p = min(1.0, 2 * sum(math.comb(n, i) for i in range(lo + 1)) / (2 ** n))
    return {
        "n_paired": len(shared),
        "crash_only": n_b,
        "correctness_only": n_c,
        "discordant": n,
        "p_exact": p,
        # A very small p rounded to four places prints 0.0, which reads as
        # "impossible" rather than "very small", so report a bound instead.
        "p_display": "<0.001" if p < 0.001 else f"{p:.3f}",
        "underpowered": n < 6,
    }


def wilson_ci(k: int, n: int, z: float = 1.959963985) -> tuple[float, float]:
    """Wilson score interval: better than the normal approximation at small n
    and at proportions near 0 or 1, which is where these cells sit."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def summarise(root: Path, pm: str, prefix: str) -> dict:
    slug = pm.replace(":", "_").replace("/", "_")
    model = pm.split(":", 1)[-1]
    crash_dir = root / f"{prefix}__{slug}__crash"
    corr_dir = root / f"{prefix}__{slug}__correctness"
    if not crash_dir.is_dir() or not corr_dir.is_dir():
        # fall back to a combined smoke-style arm holding several models
        crash_dir = root / f"{prefix}__crash"
        corr_dir = root / f"{prefix}__correctness"
        if not crash_dir.is_dir() or not corr_dir.is_dir():
            raise FileNotFoundError(f"no arm pair for {pm}")

    cd, cr, cm = load_arm(crash_dir, model)
    od, orr, om = load_arm(corr_dir, model)

    out = {"model": model, "provider": pm.split(":", 1)[0], "prefix": prefix,
           "cost_usd": round(cm["cost_usd"] + om["cost_usd"], 4),
           "errored": cm["errored"] + om["errored"]}
    for label, a, b in (("detection", cd, od), ("repair", cr, orr)):
        ka, na, kb, nb = sum(a.values()), len(a), sum(b.values()), len(b)
        la, ha = wilson_ci(ka, na)
        lb, hb = wilson_ci(kb, nb)
        out[label] = {
            "crash": {"k": ka, "n": na, "rate": round(ka / na, 4) if na else None,
                      "ci95": [round(la, 4), round(ha, 4)]},
            "correctness": {"k": kb, "n": nb, "rate": round(kb / nb, 4) if nb else None,
                            "ci95": [round(lb, 4), round(hb, 4)]},
            "mcnemar": mcnemar_exact(a, b),
        }
    return out


def _p(cell: dict) -> str:
    d = cell["mcnemar"]["p_display"]
    return r"<\,0.001" if d == "<0.001" else d


def latex_row(s: dict, headline: bool = False) -> str:
    d, r = s["detection"], s["repair"]
    name = f"\\texttt{{{s['model']}}}" + (" (headline)" if headline else "")
    return (f"    {name} & ${d['crash']['k']}$ & ${d['correctness']['k']}$ & ${_p(d)}$ "
            f"& ${r['crash']['k']}$ & ${r['correctness']['k']}$ & ${_p(r)}$ \\\\")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--prefix", default="bench", choices=["bench", "corpus", "smoke"])
    ap.add_argument("--models", nargs="*", default=[
        "fedllm:gpt-oss-120b", "openai:gpt-5-mini",
        "openai:gpt-5.4-mini", "openai:gpt-5.6-luna"])
    ap.add_argument("--latex", action="store_true")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    results, missing = [], []
    for pm in args.models:
        try:
            results.append(summarise(args.root, pm, args.prefix))
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            print(f"  ! {pm}: {exc}", file=sys.stderr)
            missing.append(pm)

    if missing:
        print(f"\nno complete pair for: {', '.join(missing)}", file=sys.stderr)
        print("An arm needs both its crash and its correctness directory before it can "
              "be paired, so a half-finished model is reported missing rather than "
              "compared against itself.\n", file=sys.stderr)

    total_cost = 0.0
    for s in results:
        d, r = s["detection"], s["repair"]
        total_cost += s["cost_usd"]
        print(f"\n{s['provider']}:{s['model']}   cost ${s['cost_usd']:.2f}"
              + (f", {s['errored']} errored records excluded" if s["errored"] else ""))
        for label, cell in (("detection", d), ("repair", r)):
            c, o, mc = cell["crash"], cell["correctness"], cell["mcnemar"]
            print(f"  {label:9s} crash {c['k']}/{c['n']} "
                  f"[{c['ci95'][0]:.2f},{c['ci95'][1]:.2f}]   "
                  f"correctness {o['k']}/{o['n']} "
                  f"[{o['ci95'][0]:.2f},{o['ci95'][1]:.2f}]   "
                  f"McNemar p = {mc['p_display']} (discordant {mc['discordant']})")
            if mc["underpowered"]:
                print(f"    NOTE: {mc['discordant']} discordant pairs. The exact test "
                      "cannot reach p < 0.05 below six whatever the split, so report "
                      "this cell as underpowered rather than as null.")

    if results:
        print(f"\ntotal cost across reported arms: ${total_cost:.2f}")

    if args.latex and results:
        print("\n% rows for tab:multimodel")
        for i, s in enumerate(results):
            print(latex_row(s, headline=(s["provider"] == "fedllm")))

    if args.out:
        args.out.write_text(json.dumps(
            {"root": str(args.root), "prefix": args.prefix,
             "results": results, "missing": missing}, indent=2))
        print(f"\nwrote {args.out}")
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
