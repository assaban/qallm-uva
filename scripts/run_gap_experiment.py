#!/usr/bin/env python3
"""Run the verification-gap experiment over a dataset of notebooks/scripts.

Examples:
    # Pilot on a small subset, free FedLLM inference
    python scripts/run_gap_experiment.py \
        --dataset data/notebooks_pilot \
        --output runs/gap_pilot \
        --llm fedllm \
        --rounds 3

    # Full dataset
    python scripts/run_gap_experiment.py \
        --dataset data/li_notebooks \
        --output runs/gap_full \
        --llm fedllm \
        --rounds 5

Produces results.jsonl (per input, resumable), aggregate.json (count-weighted
verification-gap rate across the dataset), and metrics.csv. See
docs/experiments/protocol.md for how this fits the thesis evaluation.
"""

import argparse
import logging
from pathlib import Path

from qallm.experiments.gap_runner import GapExperimentConfig, run_gap_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True,
                        help="Directory of notebooks/scripts to run.")
    parser.add_argument("--output", required=True,
                        help="Directory for results.jsonl, aggregate.json, metrics.csv.")
    parser.add_argument("--llm", default="fedllm",
                        choices=["openai", "anthropic", "ollama", "fedllm"])
    parser.add_argument("--model", default=None,
                        help="Model id; defaults to the provider's configured model.")
    parser.add_argument("--strategy", default="feedback",
                        choices=["feedback", "rl", "oneshot", "hypothesis"])
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--workers", type=int, default=1,
                        help="Parallel workers for processing files (1 = sequential; >1 runs that many files concurrently in separate processes).")
    parser.add_argument("--samples", type=int, default=1,
                        help="Consensus samples for the correctness oracle (>1 merges several generations to reduce variance; 1 = single-shot).")
    parser.add_argument("--oracle", default="crash",
                        choices=["crash", "correctness", "property", "metamorphic"])
    parser.add_argument("--judge-strategy", default="lexicographic",
                        choices=["strict", "lexicographic", "model"])
    parser.add_argument("--stage", default="implementation",
                        choices=["initialization", "implementation", "publication"])
    parser.add_argument("--pattern", default="*.ipynb",
                        help="Glob for dataset files (default *.ipynb; use *.py for scripts).")
    parser.add_argument("--confirm", action="store_true",
                        help="Also run confirm/refute (RQ2) and verify-fixes (RQ3) per "
                             "session. Makes extra LLM calls; off by default.")
    parser.add_argument("--retention", default="metrics_only",
                        choices=["full", "metrics_only"],
                        help="Artefact retention. 'metrics_only' (default) skips the "
                             "per-unit round directories and keeps the gap data in "
                             "summary.json, far less disk on large datasets. 'full' "
                             "writes every variant's provenance. --confirm forces 'full' "
                             "since it reads per-round artefacts from disk.")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--log-file", default=None,
                        help="Also write logs to this file (in addition to the "
                             "console). Useful under screen/tmux where console "
                             "scrollback is lost; tail -f it from another shell. "
                             "Defaults to <output>/run.log when omitted.")
    args = parser.parse_args()

    # Always persist a log to disk so a long run under screen/tmux can be
    # inspected later and tailed live, not just watched in a console that
    # scrolls away. Defaults to <output>/run.log.
    log_path = Path(args.log_file) if args.log_file else Path(args.output) / "run.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handlers = [logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")]
    logging.basicConfig(level=getattr(logging, args.log_level),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=handlers)
    logging.getLogger(__name__).info("Logging to %s", log_path)

    config = GapExperimentConfig(
        dataset_dir=Path(args.dataset),
        output_dir=Path(args.output),
        llm_type=args.llm,
        model_name=args.model,
        strategy=args.strategy,
        rounds=args.rounds,
        samples=args.samples,
        workers=args.workers,
        oracle=args.oracle,
        judge_strategy=args.judge_strategy,
        stage=args.stage,
        pattern=args.pattern,
        confirm=args.confirm,
        artefact_retention=args.retention,
    )
    result = run_gap_experiment(config)

    agg = result.aggregate
    print("\n=== Verification-gap experiment complete ===")
    print(f"Sessions: {len(result.per_session)}   Errors: {len(result.errors)}")
    rate = agg.get("verification_gap_rate")
    print(f"Verification gap rate: {rate if rate is not None else 'n/a (no denominator)'}")
    print(f"Execution-only bugs: {agg.get('total_execution_only_bugs')}   "
          f"Confirmed findings: {agg.get('total_confirmed_findings')}")
    if args.confirm:
        cr = agg.get("confirmation_rate")
        vr = agg.get("verified_fix_rate")
        print(f"Confirmation rate: {cr if cr is not None else 'n/a'}   "
              f"Verified-fix rate: {vr if vr is not None else 'n/a'}")
    print(f"Outputs in: {args.output}")


if __name__ == "__main__":
    main()
