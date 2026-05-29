"""QALLM entry point.

Usage:
    qallm <source> --strategy hypothesis
    qallm <source> --strategy oneshot --llm openai --model gpt-4o-mini
    qallm <source> --strategy feedback --llm openai --model gpt-4o-mini --rounds 5
"""

import argparse
import logging

from qallm.analysis.normalizer import LifecycleStage
from qallm.orchestrator import QALLMOrchestrator


def main():
    parser = argparse.ArgumentParser(description="QALLM: Quality Assessment via LLMs")
    parser.add_argument("source", help="Path to .py, .ipynb, directory, .zip, or GitHub URL")
    parser.add_argument("--strategy", default="feedback",
                        choices=["feedback", "rl", "oneshot", "hypothesis"],
                        help="Verification strategy ablation (default: feedback; "
                             "'rl' is a back-compat alias for 'feedback')")
    parser.add_argument("--llm", default="openai", choices=["openai", "anthropic", "ollama"])
    parser.add_argument("--model", default=None, help="Specific model name (e.g. gpt-4o-mini)")
    parser.add_argument("--rounds", type=int, default=5, help="Iterative feedback rounds (default: 5)")
    parser.add_argument("--oracle", default="crash", choices=["crash", "property", "metamorphic"])
    parser.add_argument("--stage", default="implementation",
                        choices=["initialization", "implementation", "publication"])
    parser.add_argument(
        "--test-stability",
        default="frozen",
        choices=["frozen", "per_round"],
        help=(
            "Whether test suites carry across QALLM rounds for the same code "
            "unit (default: frozen). frozen: yes; per_round: regenerate every round."
        ),
    )
    parser.add_argument(
        "--generation-policy",
        default="grow",
        choices=["replay_only", "grow"],
        help=(
            "Whether the LLM may add new tests for new variants (default: grow). "
            "replay_only: never (only stored tests are run). "
            "grow: yes (existing tests are kept and new ones added)."
        ),
    )
    parser.add_argument(
        "--judge-strategy",
        default="lexicographic",
        choices=["strict", "lexicographic", "model"],
        help=(
            "How the judge decides accept/abandon per round per unit "
            "(default: lexicographic). strict: any regression rejects. "
            "lexicographic: high-priority regression rejects, low-priority "
            "improvement accepts. model: LLM-driven decision with structured "
            "JSON output and Strict fallback. The model strategy adds one "
            "LLM call per round per unit; lexicographic and strict are free."
        ),
    )
    # Budget caps. Default values are sensible for a beta session; the
    # ceilings in qallm.cost override any larger value silently.
    parser.add_argument(
        "--max-tokens", type=int, default=None,
        help="Max total tokens for the session (default: 500000, ceiling: 2M).",
    )
    parser.add_argument(
        "--max-seconds", type=int, default=None,
        help="Wall-clock cap for the whole session (default: 1800, ceiling: 3600).",
    )
    parser.add_argument(
        "--max-round-seconds", type=int, default=None,
        help="Time cap per single round (default: 600, ceiling: 1200).",
    )
    parser.add_argument(
        "--max-cost-usd", type=float, default=None,
        help="Estimated USD cost cap for the session (default: 5.00, ceiling: 25.00).",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    stage = LifecycleStage(args.stage)
    # Build BudgetCaps from args, falling back to config defaults. Any
    # value above the ceilings in qallm.cost is clamped by from_kwargs.
    from qallm.cost import BudgetCaps
    from qallm.config import settings
    caps = BudgetCaps.from_kwargs(
        max_rounds=args.rounds,
        max_tokens=args.max_tokens if args.max_tokens is not None else settings.TOKEN_BUDGET,
        max_seconds=args.max_seconds if args.max_seconds is not None else settings.QALLM_MAX_SECONDS,
        max_round_seconds=args.max_round_seconds if args.max_round_seconds is not None else settings.QALLM_MAX_ROUND_SECONDS,
        max_cost_usd=args.max_cost_usd if args.max_cost_usd is not None else settings.QALLM_MAX_COST_USD,
    )
    orchestrator = QALLMOrchestrator(
        stage=stage,
        strategy=args.strategy,
        llm_type=args.llm,
        model_name=args.model,
        oracle=args.oracle,
        rounds=args.rounds,
        test_stability=args.test_stability,
        generation_policy=args.generation_policy,
        caps=caps,
        judge_strategy=args.judge_strategy,
    )

    summary = orchestrator.run(args.source)

    print(f"\n{'='*60}")
    print(f"QALLM Analysis Complete")
    print(f"{'='*60}")
    print(f"Source:   {summary['source']}")
    print(f"Strategy: {summary['strategy']}")
    print(f"Model:    {summary['model']}")
    print(f"Units:    {summary['units_analyzed']}")
    print(f"Verified: {summary['functions_verified']}")
    print(f"Cost:     ${summary['cost']['total_cost_usd']:.4f}")
    halt = summary.get("halt_reason")
    if halt and halt != "completed" and halt != "max_rounds":
        print(f"Halted:   {halt} (budget cap)")
    print()

    for s in summary["sessions"]:
        cov = s.get("final_coverage")
        cov_str = f"{cov:.1f}%" if cov is not None else "N/A"
        curve = s.get("learning_curve", [])
        curve_str = f", curve={[round(x, 2) for x in curve]}" if curve else ""
        print(f"  {s['function_name']}: coverage={cov_str}, bugs={s['final_bugs']}{curve_str}")

if __name__ == "__main__":
    main()