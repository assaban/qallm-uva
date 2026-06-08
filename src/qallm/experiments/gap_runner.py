"""Batch runner for the verification-gap track over a dataset.

Runs the QALLM pipeline across a directory of notebooks/scripts and produces
the verification-gap metric for each session plus a count-weighted aggregate,
turning the per-session work described in the experiment protocol into one
command. Results stream to JSONL so a long run is resumable, and a final
aggregate JSON and per-session CSV are written for the thesis.

Scope: by default this runner produces the verification-gap rate (RQ1),
which is derived purely from each session's persisted artefacts and needs no
extra LLM calls. With confirm=True (the --confirm CLI flag) it also runs
confirm/refute (RQ2) and verify-fixes (RQ3) per session, reconstructing their
inputs from the same artefacts (see qallm.experiments.confirm_verify); those
steps make LLM calls, so they are opt-in. All three rates flow through the
same per-session record and aggregate.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from qallm.analysis.gap_analysis import compute_gap_rounds_from_dir
from qallm.metrics_export import (
    SessionMetrics,
    aggregate_sessions,
    build_session_metrics,
    to_csv,
)

logger = logging.getLogger(__name__)


@dataclass
class GapExperimentConfig:
    dataset_dir: Path
    output_dir: Path
    llm_type: str = "fedllm"
    model_name: Optional[str] = None
    strategy: str = "feedback"
    rounds: int = 5
    oracle: str = "crash"
    judge_strategy: str = "lexicographic"
    stage: str = "implementation"
    pattern: str = "*.ipynb"  # which files in the dataset to run
    confirm: bool = False     # also run confirm/refute + verify-fixes (RQ2/RQ3); costs LLM calls

    def to_manifest(self) -> dict:
        return {
            "dataset_dir": str(self.dataset_dir),
            "llm_type": self.llm_type,
            "model_name": self.model_name,
            "strategy": self.strategy,
            "rounds": self.rounds,
            "oracle": self.oracle,
            "judge_strategy": self.judge_strategy,
            "stage": self.stage,
            "pattern": self.pattern,
            "confirm": self.confirm,
        }


@dataclass
class GapExperimentResult:
    aggregate: dict
    per_session: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


def _discover_inputs(dataset_dir: Path, pattern: str) -> list[Path]:
    """Every file under dataset_dir matching the pattern, sorted for
    determinism."""
    return sorted(dataset_dir.rglob(pattern))


def _default_orchestrator_factory(config: GapExperimentConfig):
    from qallm.orchestrator import QALLMOrchestrator
    return QALLMOrchestrator(
        strategy=config.strategy,
        llm_type=config.llm_type,
        model_name=config.model_name,
        rounds=config.rounds,
        oracle=config.oracle,
        judge_strategy=config.judge_strategy,
        stage=config.stage,
    )


def _completed_inputs(results_path: Path) -> set[str]:
    """Inputs already recorded in a prior run, for resumability."""
    done: set[str] = set()
    if not results_path.exists():
        return done
    with open(results_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["input"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def run_gap_experiment(
    config: GapExperimentConfig,
    orchestrator_factory: Optional[Callable[..., Any]] = None,
) -> GapExperimentResult:
    """Run the pipeline over the dataset and produce gap metrics + aggregate.

    Streams one JSON line per input to results.jsonl (resumable), then writes
    aggregate.json and metrics.csv. Returns the in-memory result too.
    """
    config.output_dir.mkdir(parents=True, exist_ok=True)
    results_path = config.output_dir / "results.jsonl"
    manifest_path = config.output_dir / "manifest.json"

    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(config.to_manifest(), fh, indent=2)

    if orchestrator_factory is None:
        orchestrator_factory = _default_orchestrator_factory

    inputs = _discover_inputs(config.dataset_dir, config.pattern)
    already = _completed_inputs(results_path)
    logger.info("Gap experiment: %d input(s) under %s; %d already done.",
                len(inputs), config.dataset_dir, len(already))

    metrics: list[SessionMetrics] = []
    errors: list[dict] = []

    # Re-read prior session rows so the aggregate covers the whole run, not
    # only this invocation's new sessions.
    for row in _read_jsonl(results_path):
        if row.get("error"):
            errors.append(row)
        elif row.get("metrics"):
            metrics.append(_metrics_from_dict(row["metrics"]))

    with open(results_path, "a", encoding="utf-8") as out:
        for input_path in inputs:
            key = str(input_path)
            if key in already:
                continue
            row = _run_one(input_path, config, orchestrator_factory)
            out.write(json.dumps(row) + "\n")
            out.flush()
            if row.get("error"):
                errors.append(row)
            elif row.get("metrics"):
                metrics.append(_metrics_from_dict(row["metrics"]))

    aggregate = aggregate_sessions(metrics).to_dict()
    per_session = [m.to_dict() for m in metrics]

    with open(config.output_dir / "aggregate.json", "w", encoding="utf-8") as fh:
        json.dump(aggregate, fh, indent=2)
    with open(config.output_dir / "metrics.csv", "w", encoding="utf-8") as fh:
        fh.write(to_csv(metrics))

    logger.info("Gap experiment complete: %d session(s), %d error(s). "
                "Aggregate verification_gap_rate=%s",
                len(metrics), len(errors), aggregate.get("verification_gap_rate"))
    return GapExperimentResult(aggregate=aggregate, per_session=per_session, errors=errors)


def _run_one(
    input_path: Path,
    config: GapExperimentConfig,
    orchestrator_factory: Callable[..., Any],
) -> dict:
    """Run one input and build its per-session metrics from the artefacts."""
    try:
        orch = orchestrator_factory(config)
        summary = orch.run(str(input_path))
        report_dir = summary.get("report_dir")
        gap_rounds = (
            compute_gap_rounds_from_dir(report_dir)
            if report_dir and os.path.isdir(report_dir) else []
        )
        session_id = os.path.basename(report_dir) if report_dir else str(input_path)

        confirm_summary = None
        verify_summary = None
        if config.confirm and report_dir and os.path.isdir(report_dir):
            # RQ2/RQ3: reconstruct inputs from disk and run confirm + verify.
            # Uses the orchestrator's own test-gen LLM and token tracker.
            from qallm.experiments.confirm_verify import confirm_and_verify_from_dir
            cv = confirm_and_verify_from_dir(
                report_dir,
                testgen_llm=getattr(orch, "testgen_llm", None) or getattr(orch, "llm", None),
                tracker=getattr(orch, "tracker", None),
            )
            confirm_summary = cv["confirm_summary"]
            verify_summary = cv["verify_summary"]

        m = build_session_metrics(
            session_id=session_id,
            summary=summary,
            gap_rounds=gap_rounds,
            confirm_summary=confirm_summary,
            verify_summary=verify_summary,
        )
        return {"input": str(input_path), "metrics": m.to_dict(), "error": None}
    except Exception as e:  # one bad notebook should not sink the run
        logger.warning("Input failed: %s: %s", input_path, e)
        return {"input": str(input_path), "metrics": None, "error": str(e)}


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def _metrics_from_dict(d: dict) -> SessionMetrics:
    """Rebuild a SessionMetrics from its to_dict form (for aggregation)."""
    return SessionMetrics(
        session_id=d.get("session_id", ""),
        model=d.get("model", ""),
        testgen_model=d.get("testgen_model", ""),
        oracle=d.get("oracle", ""),
        rounds=int(d.get("rounds", 0) or 0),
        units_analyzed=int(d.get("units_analyzed", 0) or 0),
        functions_verified=int(d.get("functions_verified", 0) or 0),
        cost_usd=float(d.get("cost_usd", 0.0) or 0.0),
        tokens=int(d.get("tokens", 0) or 0),
        static_findings=int(d.get("static_findings", 0) or 0),
        confirmed_findings=int(d.get("confirmed_findings", 0) or 0),
        execution_only_bugs=int(d.get("execution_only_bugs", 0) or 0),
        verification_gap_rate=d.get("verification_gap_rate"),
        confirmed=d.get("confirmed"),
        refuted=d.get("refuted"),
        confirmation_rate=d.get("confirmation_rate"),
        verified_fixed=d.get("verified_fixed"),
        not_fixed=d.get("not_fixed"),
        verified_fix_rate=d.get("verified_fix_rate"),
    )
