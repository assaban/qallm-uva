"""QALLM entry point.

Usage:
    qallm <source> --strategy hypothesis
    qallm <source> --strategy oneshot --llm openai --model gpt-4o-mini
    qallm <source> --strategy rl --llm openai --model gpt-4o-mini --rounds 5
"""

import argparse
import logging

from qallm.analysis.normalizer import LifecycleStage
from qallm.orchestrator import QALLMOrchestrator


def main():
    parser = argparse.ArgumentParser(description="QALLM: Quality Assessment via LLMs")
    parser.add_argument("source", help="Path to .py, .ipynb, directory, .zip, or GitHub URL")
    parser.add_argument("--strategy", default="rl", choices=["rl", "oneshot", "hypothesis"],
                        help="Test generation strategy (default: rl)")
    parser.add_argument("--llm", default="openai", choices=["openai", "anthropic", "ollama"])
    parser.add_argument("--model", default=None, help="Specific model name (e.g. gpt-4o-mini)")
    parser.add_argument("--rounds", type=int, default=5, help="RL feedback rounds (default: 5)")
    parser.add_argument("--oracle", default="crash", choices=["crash", "property", "metamorphic"])
    parser.add_argument("--stage", default="implementation",
                        choices=["initialization", "implementation", "publication"])
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    stage = LifecycleStage(args.stage)
    orchestrator = QALLMOrchestrator(
        stage=stage,
        strategy=args.strategy,
        llm_type=args.llm,
        model_name=args.model,
        oracle=args.oracle,
        rounds=args.rounds,
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
    print()

    for s in summary["sessions"]:
        cov = s.get("final_coverage")
        cov_str = f"{cov:.1f}%" if cov is not None else "N/A"
        curve = s.get("learning_curve", [])
        curve_str = f", curve={[round(x, 2) for x in curve]}" if curve else ""
        print(f"  {s['function']}: coverage={cov_str}, bugs={s['final_bugs']}{curve_str}")

if __name__ == "__main__":
    main()