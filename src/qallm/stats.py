"""QALLM Statistical Analysis: Wilcoxon signed-rank + Cliff's delta.

Reads the experiment CSV produced by experiment.py and computes the
statistical comparisons required for RQ1 and RQ2.

Usage:
    python -m qallm.stats outputs/experiments/20260505_120000/results.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


def cliffs_delta(x: list[float], y: list[float]) -> tuple[float, str]:
    """Compute Cliff's delta effect size between two samples.

    Returns (delta, interpretation) where interpretation is one of:
    'negligible', 'small', 'medium', 'large'.

    Cliff's delta ranges from -1 to +1.
    Thresholds follow Romano et al. (2006):
      |d| < 0.147: negligible
      |d| < 0.33:  small
      |d| < 0.474: medium
      |d| >= 0.474: large
    """
    n_x, n_y = len(x), len(y)
    if n_x == 0 or n_y == 0:
        return 0.0, "negligible"

    more = sum(1 for xi in x for yi in y if xi > yi)
    less = sum(1 for xi in x for yi in y if xi < yi)
    delta = (more - less) / (n_x * n_y)

    abs_d = abs(delta)
    if abs_d < 0.147:
        interp = "negligible"
    elif abs_d < 0.33:
        interp = "small"
    elif abs_d < 0.474:
        interp = "medium"
    else:
        interp = "large"

    return round(delta, 4), interp


def wilcoxon_test(x: list[float], y: list[float], alpha: float = 0.05) -> dict:
    """Paired Wilcoxon signed-rank test.

    Returns dict with statistic, p_value, significant, and effect_size.
    Requires scipy.
    """
    from scipy.stats import wilcoxon

    # Filter pairs where both are non-zero (Wilcoxon requires differences != 0)
    pairs = [(a, b) for a, b in zip(x, y) if a != b]
    if len(pairs) < 5:
        return {
            "statistic": None,
            "p_value": None,
            "significant": False,
            "note": f"Insufficient non-tied pairs ({len(pairs)} < 5)",
        }

    x_filtered = [p[0] for p in pairs]
    y_filtered = [p[1] for p in pairs]

    stat, p_val = wilcoxon(x_filtered, y_filtered)
    delta, delta_interp = cliffs_delta(x, y)

    return {
        "statistic": round(float(stat), 4),
        "p_value": round(float(p_val), 6),
        "significant": p_val < alpha,
        "cliffs_delta": delta,
        "effect_size": delta_interp,
        "n_pairs": len(pairs),
        "alpha": alpha,
    }


def load_results(csv_path: str) -> list[dict]:
    """Load experiment results from CSV."""
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Parse numeric fields
            for key in ("passed", "failed", "errors", "bugs_found", "tokens_used"):
                row[key] = int(row.get(key) or 0)
            for key in ("coverage", "cost_usd"):
                val = row.get(key, "")
                row[key] = float(val) if val and val != "None" else 0.0
            rows.append(row)
    return rows


def group_by_function(rows: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """Group rows by function name, then by strategy.

    Returns {function_name: {strategy: [rows]}}
    """
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row["function"]][row["strategy"]].append(row)
    return grouped


def analyze_rq1(csv_path: str) -> None:
    """RQ1: How effectively can RL-guided test generation assess functional
    correctness compared to baselines?

    Compares: hypothesis vs oneshot vs rl on bug-finding rate, coverage,
    and test validity.
    """
    rows = load_results(csv_path)
    strategies = sorted(set(r["strategy"] for r in rows))

    print("\n" + "=" * 70)
    print("RQ1: THREE-STRATEGY COMPARISON")
    print("=" * 70)

    # Aggregate per strategy
    for strategy in strategies:
        strat_rows = [r for r in rows if r["strategy"] == strategy]
        total_bugs = sum(r["bugs_found"] for r in strat_rows)
        coverages = [r["coverage"] for r in strat_rows if r["coverage"] > 0]
        avg_cov = sum(coverages) / len(coverages) if coverages else 0.0
        total_tokens = sum(r["tokens_used"] for r in strat_rows)
        total_cost = sum(r["cost_usd"] for r in strat_rows)
        n_functions = len(strat_rows)

        print(f"\n  {strategy}")
        print(f"    Functions tested:  {n_functions}")
        print(f"    Total bugs found: {total_bugs}")
        print(f"    Avg coverage:     {avg_cov:.1f}%")
        print(f"    Total tokens:     {total_tokens:,}")
        print(f"    Total cost:       ${total_cost:.4f}")

    # Pairwise comparisons on bug-finding rate
    print("\n" + "-" * 70)
    print("PAIRWISE COMPARISONS (Bug-finding rate)")
    print("-" * 70)

    # Group by function to get paired observations
    grouped = group_by_function(rows)

    for s1 in strategies:
        for s2 in strategies:
            if s1 >= s2:
                continue

            bugs_s1, bugs_s2 = [], []
            for func_name, strat_data in grouped.items():
                if s1 in strat_data and s2 in strat_data:
                    bugs_s1.append(sum(r["bugs_found"] for r in strat_data[s1]))
                    bugs_s2.append(sum(r["bugs_found"] for r in strat_data[s2]))

            if len(bugs_s1) < 5:
                print(f"\n  {s1} vs {s2}: insufficient paired observations ({len(bugs_s1)})")
                continue

            result = wilcoxon_test(bugs_s1, bugs_s2)
            print(f"\n  {s1} vs {s2}")
            print(f"    Paired functions: {result.get('n_pairs', len(bugs_s1))}")
            print(f"    Wilcoxon W:       {result['statistic']}")
            print(f"    p-value:          {result['p_value']}")
            print(f"    Significant:      {'YES' if result['significant'] else 'no'} (alpha={result.get('alpha', 0.05)})")
            print(f"    Cliff's delta:    {result.get('cliffs_delta', 'N/A')} ({result.get('effect_size', 'N/A')})")

    # Same for coverage
    print("\n" + "-" * 70)
    print("PAIRWISE COMPARISONS (Coverage)")
    print("-" * 70)

    for s1 in strategies:
        for s2 in strategies:
            if s1 >= s2:
                continue

            cov_s1, cov_s2 = [], []
            for func_name, strat_data in grouped.items():
                if s1 in strat_data and s2 in strat_data:
                    cov_s1.append(max((r["coverage"] for r in strat_data[s1]), default=0))
                    cov_s2.append(max((r["coverage"] for r in strat_data[s2]), default=0))

            if len(cov_s1) < 5:
                print(f"\n  {s1} vs {s2}: insufficient paired observations ({len(cov_s1)})")
                continue

            result = wilcoxon_test(cov_s1, cov_s2)
            print(f"\n  {s1} vs {s2}")
            print(f"    Paired functions: {result.get('n_pairs', len(cov_s1))}")
            print(f"    Wilcoxon W:       {result['statistic']}")
            print(f"    p-value:          {result['p_value']}")
            print(f"    Significant:      {'YES' if result['significant'] else 'no'}")
            print(f"    Cliff's delta:    {result.get('cliffs_delta', 'N/A')} ({result.get('effect_size', 'N/A')})")


def analyze_rq2(csv_path: str) -> None:
    """RQ2: False confidence rate analysis.

    Compares static-only assessment vs static + RL verification.
    """
    rows = load_results(csv_path)

    print("\n" + "=" * 70)
    print("RQ2: FALSE CONFIDENCE RATE")
    print("=" * 70)

    # Find RL strategy rows (they have the verification results)
    rl_rows = [r for r in rows if r["strategy"].startswith("rl_")]

    if not rl_rows:
        print("  No RL results found in CSV. Run with --strategy rl first.")
        return

    # A function is "clean by static" if the static analysis found no issues
    # We approximate this: if coverage > 0, the function was testable
    # If bugs_found > 0, execution found issues that static missed
    testable = [r for r in rl_rows if r["coverage"] > 0]
    with_bugs = [r for r in testable if r["bugs_found"] > 0]

    if testable:
        fcr = len(with_bugs) / len(testable)
        print(f"\n  Testable functions:    {len(testable)}")
        print(f"  Functions with bugs:   {len(with_bugs)}")
        print(f"  False confidence rate: {fcr:.1%}")
        print(f"  (Proportion of testable code where execution found defects)")
    else:
        print("  No testable functions found.")


def main():
    parser = argparse.ArgumentParser(description="QALLM Statistical Analysis")
    parser.add_argument("csv_path", help="Path to experiment results CSV")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    analyze_rq1(args.csv_path)
    analyze_rq2(args.csv_path)


if __name__ == "__main__":
    main()
