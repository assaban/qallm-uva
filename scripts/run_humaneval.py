#!/usr/bin/env python
"""Run the HumanEvalFix experiment.

Example:

    # Pilot with 5 sampled problems, RL only, single model:
    python scripts/run_humaneval.py \\
        --output runs/heval_pilot \\
        --strategies rl \\
        --models openai:gpt-4o-mini \\
        --sample-size 5 \\
        --rounds 3

    # Full run, all strategies, two models:
    python scripts/run_humaneval.py \\
        --output runs/heval_full \\
        --strategies rl,oneshot,hypothesis \\
        --models openai:gpt-4o-mini,ollama:gemma3:4b \\
        --rounds 5

Resumability:
    Results are written to ``<output>/results.jsonl`` one per line as each
    combination completes. Re-running the same command after a crash
    automatically skips combinations already recorded.

Cost warning:
    A full run (164 problems x 3 strategies x N models, with hypothesis
    being free) will cost real money on OpenAI/Anthropic providers.
    Estimate before triggering: roughly 1k-3k tokens per round per
    problem; 164 problems x 5 rounds x 2 strategies = ~1.5M-5M tokens
    per paid model. On gpt-4o-mini that is roughly $0.40-$1.50 USD.
    Larger models scale accordingly.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the HumanEvalFix experiment for QALLM validation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output", required=True,
        help="Directory to write results.jsonl, aggregates.json, report.md.",
    )
    parser.add_argument(
        "--models", required=True,
        help="Comma-separated model ids (e.g. openai:gpt-4o-mini,ollama:gemma3:4b).",
    )
    parser.add_argument(
        "--strategies", default="rl,oneshot,hypothesis",
        help="Comma-separated strategies (default: rl,oneshot,hypothesis).",
    )
    parser.add_argument(
        "--sample-size", type=int, default=None,
        help="If set, run on a deterministic random subset of this size.",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Sampling seed (default 42). Recorded in the manifest.",
    )
    parser.add_argument(
        "--rounds", type=int, default=5,
        help="QALLM rounds per run (default 5).",
    )
    parser.add_argument(
        "--oracle", default="crash", choices=["crash", "property", "metamorphic"],
        help="Test oracle (default crash).",
    )
    parser.add_argument(
        "--judge-strategy", default="lexicographic",
        choices=["strict", "lexicographic", "model"],
        help="Judge strategy (default lexicographic).",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default INFO).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from qallm.experiments.humaneval_runner import (
        ExperimentConfig, run_experiment,
    )

    config = ExperimentConfig(
        output_dir=Path(args.output),
        models=[m.strip() for m in args.models.split(",") if m.strip()],
        strategies=[s.strip() for s in args.strategies.split(",") if s.strip()],
        sample_size=args.sample_size,
        seed=args.seed,
        rounds=args.rounds,
        oracle=args.oracle,
        judge_strategy=args.judge_strategy,
    )

    if not config.models or not config.strategies:
        parser.error("At least one model and one strategy are required.")

    print(f"Output: {config.output_dir}")
    print(f"Models: {', '.join(config.models)}")
    print(f"Strategies: {', '.join(config.strategies)}")
    print(f"Sample size: {config.sample_size or 'all 164'}")
    print(f"Rounds: {config.rounds}, oracle: {config.oracle}, "
          f"judge: {config.judge_strategy}, seed: {config.seed}")
    print("Starting...")

    results = run_experiment(config)

    print(f"Done. {len(results)} results.")
    print(f"Report: {config.output_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
