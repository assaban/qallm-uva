"""QALLM Experiment Runner: batch execution for RQ1 three-strategy comparison.

Runs Hypothesis baseline, one-shot LLM, and RL-guided verification on a
list of notebooks/source files and aggregates results into a single CSV
for statistical analysis (Wilcoxon signed-rank + Cliff's delta).

Usage:
    python -m qallm.experiment --input data/pilot/ --models gpt-4o-mini --rounds 5
    python -m qallm.experiment --input data/li_dataset/subset/ --models gpt-4o-mini,gpt-5-mini --rounds 5
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import datetime
from pathlib import Path

from qallm.config import settings
from qallm.ingestion.ingestion_manager import IngestionManager
from qallm.llm.base import TokenTracker
from qallm.llm.openai_provider import OpenAIModel
from qallm.llm.anthropic_provider import AnthropicModel
from qallm.llm.ollama_provider import OllamaModel
from qallm.verification.extractor import extract_functions_from_source
from qallm.verification.loop import TestGenerationLoop
from qallm.verification.models import OracleType

logger = logging.getLogger(__name__)

LLM_PROVIDERS = {
    "openai": OpenAIModel,
    "anthropic": AnthropicModel,
    "ollama": OllamaModel,
}


def _build_llm(model_name: str):
    """Create the right LLM provider based on model name prefix."""
    if model_name.startswith("gpt"):
        return OpenAIModel(model_name)
    elif model_name.startswith("claude"):
        return AnthropicModel(model_name)
    else:
        return OllamaModel(model_name)


def run_hypothesis_strategy(source_code: str, source_filename: str, source_origin: Path | None) -> list[dict]:
    """Strategy (a): Hypothesis property-based testing."""
    from qallm.verification.hypothesis_baseline import run_hypothesis_baseline
    return run_hypothesis_baseline(source_code, source_filename, source_origin)


def run_oneshot_strategy(source_code: str, source_filename: str, source_origin: Path | None,
                         model_name: str, oracle: OracleType) -> list[dict]:
    """Strategy (b): One-shot LLM, no feedback."""
    llm = _build_llm(model_name)
    tracker = TokenTracker(budget=settings.TOKEN_BUDGET)
    functions = extract_functions_from_source(source_code, source_filename)
    results = []

    loop = TestGenerationLoop(llm=llm, rounds=1, oracle=oracle, tracker=tracker)
    for func in functions:
        module_name = f"source_{Path(source_filename).stem}"
        session = loop.run(func=func, source_code=source_code, module_name=module_name,
                           source_origin=source_origin)
        last_round = session.rounds[-1] if session.rounds else None
        results.append({
            "function": func.name,
            "strategy": f"oneshot_{model_name}",
            "passed": last_round.execution.passed if last_round else 0,
            "failed": last_round.execution.failed if last_round else 0,
            "errors": last_round.execution.errors if last_round else 0,
            "coverage": session.final_coverage,
            "bugs_found": session.final_bugs,
            "tokens_used": tracker.total_tokens,
            "cost_usd": tracker.total_cost_usd,
        })
    return results


def run_rl_strategy(source_code: str, source_filename: str, source_origin: Path | None,
                    model_name: str, oracle: OracleType, rounds: int) -> list[dict]:
    """Strategy (c): RL-guided with N rounds of feedback."""
    llm = _build_llm(model_name)
    tracker = TokenTracker(budget=settings.TOKEN_BUDGET)
    functions = extract_functions_from_source(source_code, source_filename)
    results = []

    loop = TestGenerationLoop(llm=llm, rounds=rounds, oracle=oracle, tracker=tracker)
    for func in functions:
        module_name = f"source_{Path(source_filename).stem}"
        session = loop.run(func=func, source_code=source_code, module_name=module_name,
                           source_origin=source_origin)
        results.append({
            "function": func.name,
            "strategy": f"rl_{model_name}_{rounds}r",
            "passed": sum(r.execution.passed for r in session.rounds),
            "failed": sum(r.execution.failed for r in session.rounds),
            "errors": sum(r.execution.errors for r in session.rounds),
            "coverage": session.final_coverage,
            "bugs_found": session.final_bugs,
            "learning_curve": session.learning_curve,
            "curve_slope": (session.learning_curve[-1] - session.learning_curve[0]) / max(1, len(session.learning_curve) - 1) if len(session.learning_curve) > 1 else 0.0,
            "tokens_used": tracker.total_tokens,
            "cost_usd": tracker.total_cost_usd,
        })
    return results


def collect_source_files(input_path: str) -> list[Path]:
    """Collect all .py and .ipynb files from the input path."""
    p = Path(input_path)
    if p.is_file():
        return [p]
    files = sorted(p.rglob("*.py")) + sorted(p.rglob("*.ipynb"))
    # Skip __init__.py, setup.py, config-only files
    return [f for f in files if f.stem not in ("__init__", "setup", "conftest")]


def run_experiment(
    input_path: str,
    models: list[str],
    rounds: int = 5,
    oracle: OracleType = "crash",
    output_dir: str = "outputs/experiments",
) -> Path:
    """Run the full three-strategy comparison and write results to CSV."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(output_dir) / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "results.csv"
    fieldnames = [
        "file", "function", "strategy", "passed", "failed", "errors",
        "coverage", "bugs_found", "tokens_used", "cost_usd",
        "learning_curve", "curve_slope",
    ]

    ingestion = IngestionManager()
    source_files = collect_source_files(input_path)
    logger.info("Experiment: %d files, %d models, %d rounds, oracle=%s",
                len(source_files), len(models), rounds, oracle)

    all_rows = []

    for file_idx, source_file in enumerate(source_files):
        logger.info("[%d/%d] Processing: %s", file_idx + 1, len(source_files), source_file.name)

        try:
            units = ingestion.collect(str(source_file))
        except Exception as e:
            logger.warning("Skipping %s: ingestion error: %s", source_file.name, e)
            continue

        for unit in units:
            source_code = unit.source_code
            source_filename = f"source_{unit.original_path.stem}_c{unit.cell_index}.py"

            # Strategy (a): Hypothesis (once per file, no model variation)
            logger.info("  Strategy: hypothesis")
            try:
                hyp_results = run_hypothesis_strategy(source_code, source_filename, unit.original_path)
                for r in hyp_results:
                    r["file"] = source_file.name
                    r["tokens_used"] = 0
                    r["cost_usd"] = 0.0
                    r["learning_curve"] = ""
                    r["curve_slope"] = ""
                    all_rows.append(r)
            except Exception as e:
                logger.warning("  Hypothesis failed on %s: %s", source_file.name, e)

            # Strategy (b) and (c) for each model
            for model_name in models:
                # Strategy (b): One-shot
                logger.info("  Strategy: oneshot (%s)", model_name)
                try:
                    oneshot_results = run_oneshot_strategy(
                        source_code, source_filename, unit.original_path, model_name, oracle)
                    for r in oneshot_results:
                        r["file"] = source_file.name
                        r["learning_curve"] = ""
                        r["curve_slope"] = ""
                        all_rows.append(r)
                except Exception as e:
                    logger.warning("  Oneshot %s failed on %s: %s", model_name, source_file.name, e)

                # Strategy (c): RL-guided
                logger.info("  Strategy: rl (%s, %d rounds)", model_name, rounds)
                try:
                    rl_results = run_rl_strategy(
                        source_code, source_filename, unit.original_path, model_name, oracle, rounds)
                    for r in rl_results:
                        r["file"] = source_file.name
                        r["learning_curve"] = str(r.get("learning_curve", ""))
                        r["curve_slope"] = str(r.get("curve_slope", ""))
                        all_rows.append(r)
                except Exception as e:
                    logger.warning("  RL %s failed on %s: %s", model_name, source_file.name, e)

    # Write CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)

    # Write experiment metadata
    meta = {
        "timestamp": timestamp,
        "input_path": input_path,
        "files_processed": len(source_files),
        "models": models,
        "rounds": rounds,
        "oracle": oracle,
        "total_rows": len(all_rows),
        "csv_path": str(csv_path),
    }
    (out_dir / "experiment_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    logger.info("Experiment complete: %d rows written to %s", len(all_rows), csv_path)
    return csv_path


def main():
    parser = argparse.ArgumentParser(description="QALLM Experiment Runner")
    parser.add_argument("--input", required=True, help="Path to notebooks/source files")
    parser.add_argument("--models", default="gpt-4o-mini", help="Comma-separated model names")
    parser.add_argument("--rounds", type=int, default=5, help="RL feedback rounds")
    parser.add_argument("--oracle", default="crash", choices=["crash", "correctness", "property", "metamorphic"])
    parser.add_argument("--output", default="outputs/experiments", help="Output directory")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    models = [m.strip() for m in args.models.split(",")]

    csv_path = run_experiment(
        input_path=args.input,
        models=models,
        rounds=args.rounds,
        oracle=args.oracle,
        output_dir=args.output,
    )

    print(f"\nResults: {csv_path}")


if __name__ == "__main__":
    main()
