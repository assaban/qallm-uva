"""QALLM entry point.

Usage:
    python -m qallm.run_qallm <source_path> [--llm openai|anthropic|ollama] [--rounds 5] [--oracle crash|property|metamorphic]
"""

import argparse
import logging
import sys

from qallm.analysis.normalizer import LifecycleStage
from qallm.orchestrator import QALLMOrchestrator


def main():
    parser = argparse.ArgumentParser(description="QALLM: Quality Assessment via LLMs")
    parser.add_argument("source", help="Path to .py, .ipynb, directory, .zip, or GitHub URL")
    parser.add_argument("--llm", default="openai", choices=["openai", "anthropic", "ollama"])
    parser.add_argument("--model", default=None, help="Specific model name (e.g. gpt-4o-mini)")
    parser.add_argument("--rounds", type=int, default=5, help="RL feedback rounds (1-10)")
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
        llm_type=args.llm,
        model_name=args.model,
        oracle=args.oracle,
        rounds=args.rounds,
    )

    summary = orchestrator.run(args.source)

    print(f"\n{'='*60}")
    print(f"QALLM Analysis Complete")
    print(f"{'='*60}")
    print(f"Source: {summary['source']}")
    print(f"Model: {summary['model']}")
    print(f"Units analyzed: {summary['units_analyzed']}")
    print(f"Functions verified: {summary['functions_verified']}")
    print(f"Total cost: ${summary['cost']['total_cost_usd']:.4f}")
    print()

    for s in summary["sessions"]:
        print(f"  {s['function']}: coverage={s['final_coverage']:.1f}%, "
              f"bugs={s['final_bugs']}, curve={s['learning_curve']}")


if __name__ == "__main__":
    main()
