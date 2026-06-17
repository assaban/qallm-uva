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
import traceback
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
    samples: int = 1  # consensus samples for the correctness oracle (1 = single-shot)
    oracle: str = "crash"
    judge_strategy: str = "lexicographic"
    stage: str = "implementation"
    pattern: str = "*.ipynb"  # which files in the dataset to run
    confirm: bool = False     # also run confirm/refute + verify-fixes (RQ2/RQ3); costs LLM calls
    # Batch runs default to metrics_only: skip the per-unit round directories
    # (thousands of small files across a dataset) and keep the gap data in
    # summary.json. Pass "full" to retain every variant's provenance.
    artefact_retention: str = "metrics_only"
    # Parallel workers for processing files. 1 = sequential (default, identical
    # to the historical behaviour). >1 processes that many files concurrently
    # in separate processes; each file is an independent orchestrator/session,
    # so this is safe. Bound by LLM-API concurrency limits in practice.
    workers: int = 1
    # Log level workers configure for themselves (they do not inherit the main
    # process's logging config under the spawn start method). The log file is
    # output_dir/run.log, matching the main process.
    log_level: str = "INFO"
    # Opt-in: after the gap is measured, mutation-test the oracle for each
    # execution-only (gap) function and attach a confidence. Needs full
    # retention (reads round-0 source and tests from disk), like --confirm.
    mutation_confidence: bool = False
    # Sampling: run a representative subset instead of the whole dataset, useful
    # for a fast signal while the full run is still going. sample_n=0 means no
    # sampling (run everything). Stratified sampling buckets files by size so the
    # subset spans small/medium/large rather than over-representing one band.
    sample_n: int = 0
    sample_seed: int = 42
    sample_stratify: bool = False

    def to_manifest(self) -> dict:
        return {
            "dataset_dir": str(self.dataset_dir),
            "llm_type": self.llm_type,
            "model_name": self.model_name,
            "strategy": self.strategy,
            "rounds": self.rounds,
            "samples": self.samples,
            "oracle": self.oracle,
            "judge_strategy": self.judge_strategy,
            "stage": self.stage,
            "pattern": self.pattern,
            "confirm": self.confirm,
            "workers": self.workers,
            "mutation_confidence": self.mutation_confidence,
        }


@dataclass
class GapExperimentResult:
    aggregate: dict
    per_session: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


def _is_backup_or_cruft(path: Path) -> bool:
    """True for files that are not real dataset inputs.

    rglob over a real-world dataset catches more than the intended notebooks:
    Jupyter autosave copies (under .ipynb_checkpoints, or named
    *-checkpoint.ipynb), editor backups (foo.ipynb~, foo.py.bak, foo.py.orig),
    and macOS AppleDouble sidecars (._foo.ipynb). Processing these
    double-counts the same code or feeds junk to the pipeline, wasting budget
    and skewing the gap rate. Exclude them so a run uses only canonical inputs.
    """
    name = path.name
    if ".ipynb_checkpoints" in path.parts:
        return True
    if name.startswith("._"):  # macOS AppleDouble sidecar
        return True
    if name.endswith((".ipynb~", ".py~", ".bak", ".orig", ".tmp", ".swp")):
        return True
    if name.endswith("-checkpoint.ipynb"):  # Jupyter checkpoint outside the dir
        return True
    return False


def _discover_inputs(dataset_dir: Path, pattern: str) -> list[Path]:
    """Every canonical file under dataset_dir matching the pattern, sorted for
    determinism.

    Backups and editor/Jupyter/OS cruft are excluded (see
    _is_backup_or_cruft): they are duplicates or junk that rglob would
    otherwise feed to the pipeline, double-processing code and wasting budget.
    """
    return sorted(
        p for p in dataset_dir.rglob(pattern)
        if not _is_backup_or_cruft(p)
    )


def _sample_inputs(inputs: list[Path], n: int, seed: int,
                   stratify: bool) -> list[Path]:
    """Pick a representative subset of n inputs.

    With stratify=False this is a plain uniform random sample. With
    stratify=True the inputs are bucketed by file size into small/medium/large
    (tertiles) and sampled proportionally, so the subset spans the size range
    rather than over-representing whichever band is most common. The result is
    sorted for determinism, and the seed makes the choice reproducible (so the
    sampled run can be cited and repeated).
    """
    import random
    if n <= 0 or n >= len(inputs):
        return inputs
    rng = random.Random(seed)
    if not stratify:
        return sorted(rng.sample(inputs, n))

    sized = sorted(inputs, key=lambda p: p.stat().st_size)
    third = len(sized) // 3 or 1
    bands = [sized[:third], sized[third:2 * third], sized[2 * third:]]
    picked: list[Path] = []
    # proportional allocation, with at least one from each non-empty band
    for band in bands:
        if not band:
            continue
        share = max(1, round(n * len(band) / len(sized)))
        picked.extend(rng.sample(band, min(share, len(band))))
    # trim or top up to exactly n
    picked = list(dict.fromkeys(picked))
    if len(picked) > n:
        picked = rng.sample(picked, n)
    elif len(picked) < n:
        remaining = [p for p in inputs if p not in set(picked)]
        picked.extend(rng.sample(remaining, min(n - len(picked), len(remaining))))
    return sorted(picked)


def _effective_retention(config: GapExperimentConfig) -> str:
    """Resolve retention, accounting for confirm's disk dependency.

    confirm/refute and verify-fixes reconstruct their inputs from the on-disk
    round_0 artefacts, so metrics_only (which does not write them) is
    incompatible with --confirm. When both are requested, full retention wins
    and the caller is told why.
    """
    if (config.confirm or config.mutation_confidence) and config.artefact_retention == "metrics_only":
        reason = "--confirm" if config.confirm else "--mutation-confidence"
        logger.info(
            "artefact_retention=metrics_only is incompatible with %s "
            "(it reads per-round artefacts from disk); using 'full'.", reason,
        )
        return "full"
    return config.artefact_retention


def _default_orchestrator_factory(config: GapExperimentConfig):
    from qallm.orchestrator import QALLMOrchestrator
    return QALLMOrchestrator(
        strategy=config.strategy,
        llm_type=config.llm_type,
        model_name=config.model_name,
        rounds=config.rounds,
        samples=config.samples,
        oracle=config.oracle,
        judge_strategy=config.judge_strategy,
        artefact_retention=_effective_retention(config),
        stage=config.stage,
        # Reporter artefacts live UNDER this run's own output dir, not the
        # shared Web-UI session directory. Each experiment run is then fully
        # self-contained: deleting runs/<name> removes its artefacts too, and a
        # large run never bloats outputs/quality_reporter.
        reporter_dir=str(config.output_dir / "reports"),
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

    if orchestrator_factory is None:
        orchestrator_factory = _default_orchestrator_factory

    inputs = _discover_inputs(config.dataset_dir, config.pattern)
    discovered = len(inputs)
    if config.sample_n and config.sample_n < discovered:
        inputs = _sample_inputs(inputs, config.sample_n, config.sample_seed,
                                config.sample_stratify)
        logger.info(
            "Sampling %d of %d input(s) (seed=%d, stratify=%s).",
            len(inputs), discovered, config.sample_seed, config.sample_stratify,
        )

    # Manifest = config + provenance (commit, version, env, dataset
    # fingerprint), so every number from this run traces back to exact
    # conditions. Provenance is best-effort and never blocks the run.
    from qallm.experiments.provenance import capture, dataset_fingerprint
    manifest = config.to_manifest()
    try:
        manifest["provenance"] = capture(
            {"dataset": dataset_fingerprint(inputs)}
        )
    except Exception as exc:  # provenance must never sink a run
        logger.warning("Provenance capture failed: %s", exc)
        manifest["provenance"] = {"error": repr(exc)}
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    already = _completed_inputs(results_path)
    logger.info("Gap experiment: %d input(s) under %s; %d already done.",
                len(inputs), config.dataset_dir, len(already))

    metrics: list[SessionMetrics] = []
    errors: list[dict] = []
    # Per-session gap-confidence blocks (present only with --mutation-confidence),
    # combined into a run-level distribution for the aggregate.
    confidence_blocks: list[dict] = []

    # Re-read prior session rows so the aggregate covers the whole run, not
    # only this invocation's new sessions.
    for row in _read_jsonl(results_path):
        if row.get("error"):
            errors.append(row)
        elif row.get("metrics"):
            metrics.append(_metrics_from_dict(row["metrics"]))
        if row.get("gap_confidence"):
            confidence_blocks.append(row["gap_confidence"])

    pending = [p for p in inputs if str(p) not in already]
    # Progress is counted against the whole run (already-done + this run's
    # pending), so the percentage reflects true position in the dataset, not
    # just this invocation. A single counter, incremented as rows land.
    total_target = len(already) + len(pending)
    progress = {"done": len(already)}

    def _log_progress(input_path: str) -> None:
        progress["done"] += 1
        pct = (100.0 * progress["done"] / total_target) if total_target else 100.0
        logger.info("Progress: %d/%d (%.1f%%) complete; last=%s",
                    progress["done"], total_target, pct,
                    os.path.basename(input_path))

    def _handle_row(row: dict) -> None:
        out.write(json.dumps(row) + "\n")
        out.flush()
        if row.get("error"):
            errors.append(row)
        elif row.get("metrics"):
            metrics.append(_metrics_from_dict(row["metrics"]))
        if row.get("gap_confidence"):
            confidence_blocks.append(row["gap_confidence"])
        _log_progress(row.get("input", "?"))

    with open(results_path, "a", encoding="utf-8") as out:
        if config.workers and config.workers > 1 and len(pending) > 1:
            logger.info("Processing %d file(s) with %d parallel worker(s).",
                        len(pending), config.workers)
            # Each file is an independent orchestrator/session, so files run
            # in separate processes safely. Results are written as they
            # complete (order may differ from input order; the aggregate is
            # order-independent and each row carries its own input path).
            from concurrent.futures import ProcessPoolExecutor, as_completed
            log_path = config.output_dir / "run.log"
            with ProcessPoolExecutor(
                max_workers=config.workers,
                initializer=_init_worker_logging,
                initargs=(str(log_path), config.log_level),
            ) as pool:
                futures = {
                    pool.submit(_run_one, p, config, orchestrator_factory): p
                    for p in pending
                }
                for fut in as_completed(futures):
                    input_path = futures[fut]
                    try:
                        row = fut.result()
                    except Exception as exc:  # a worker crashed; record it
                        logger.exception("Worker failed for %s", input_path)
                        row = {"input": str(input_path), "error": repr(exc)}
                    _handle_row(row)
        else:
            for input_path in pending:
                row = _run_one(input_path, config, orchestrator_factory)
                _handle_row(row)

    aggregate = aggregate_sessions(metrics).to_dict()
    per_session = [m.to_dict() for m in metrics]

    # Surface errored inputs in the aggregate, not just the log. Without this a
    # reader of aggregate.json cannot tell "measured and clean" from "could not
    # be measured": a batch that silently drops a tenth of its inputs would look
    # identical to one where every input was analysed. The headline rate is over
    # measured inputs; the error accounting makes the denominator honest. The
    # by-type breakdown surfaces a recurring failure (e.g. one ingestion bug)
    # instead of burying it in the per-input log.
    n_ok = len(metrics)
    n_errored = len(errors)
    n_total = n_ok + n_errored
    error_types: dict[str, int] = {}
    for e in errors:
        msg = str(e.get("error", "unknown"))
        # Collapse to a short signature so similar errors group together.
        sig = msg.split("\n")[0][:80]
        error_types[sig] = error_types.get(sig, 0) + 1
    aggregate["inputs"] = {
        "total": n_total,
        "measured": n_ok,
        "errored": n_errored,
        "errored_fraction": round(n_errored / n_total, 4) if n_total else 0.0,
        "error_types": dict(sorted(error_types.items(),
                                   key=lambda kv: kv[1], reverse=True)),
    }

    # When mutation-confidence ran, add a run-level confidence distribution and
    # a high-confidence gap count, so the headline can be reported filtered to
    # high-confidence findings (direct evidence the gap is not test noise).
    if confidence_blocks:
        combined = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
        scored = 0
        for block in confidence_blocks:
            for label, n in (block.get("distribution") or {}).items():
                combined[label] = combined.get(label, 0) + int(n or 0)
            scored += int(block.get("scored", 0) or 0)
        aggregate["gap_confidence"] = {
            "distribution": combined,
            "scored": scored,
            "high_confidence_gap_bugs": combined.get("high", 0),
        }
        logger.info("Gap-confidence distribution over the run: %s", combined)

    with open(config.output_dir / "aggregate.json", "w", encoding="utf-8") as fh:
        json.dump(aggregate, fh, indent=2)
    with open(config.output_dir / "metrics.csv", "w", encoding="utf-8") as fh:
        fh.write(to_csv(metrics))

    logger.info("Gap experiment complete: %d session(s), %d error(s). "
                "Aggregate verification_gap_rate=%s",
                len(metrics), len(errors), aggregate.get("verification_gap_rate"))
    return GapExperimentResult(aggregate=aggregate, per_session=per_session, errors=errors)


def _init_worker_logging(log_path: str, log_level: str) -> None:
    """Configure logging inside a pool worker process.

    ProcessPoolExecutor workers are fresh interpreters (spawn start method on
    macOS and Windows) and do NOT inherit the main process's logging config, so
    without this a parallel run is silent: all per-file work happens in workers
    that log to nowhere, and the main log only shows start/finish. Each worker
    attaches its own handlers to the SAME run.log (FileHandler appends, so
    workers interleave into one file) plus stderr, and prefixes each line with
    the worker pid so interleaved lines are attributable.
    """
    import logging as _logging
    import os

    root = _logging.getLogger()
    # Guard against double-configuration if the initializer runs more than once.
    if getattr(root, "_qallm_worker_configured", False):
        return
    level = getattr(_logging, log_level, _logging.INFO)
    fmt = _logging.Formatter(
        f"%(asctime)s %(levelname)s [pid {os.getpid()}] %(name)s: %(message)s"
    )
    file_h = _logging.FileHandler(log_path, encoding="utf-8")
    file_h.setFormatter(fmt)
    stream_h = _logging.StreamHandler()
    stream_h.setFormatter(fmt)
    root.setLevel(level)
    root.addHandler(file_h)
    root.addHandler(stream_h)
    root._qallm_worker_configured = True


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
        # Prefer gap rounds persisted in the summary (metrics_only retention,
        # where per-round artefacts are not on disk). Fall back to reading the
        # per-round directories when running with full retention.
        if summary.get("gap_rounds"):
            gap_rounds = summary["gap_rounds"]
        elif report_dir and os.path.isdir(report_dir):
            gap_rounds = compute_gap_rounds_from_dir(report_dir)
        else:
            gap_rounds = []
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

        gap_confidence = None
        if config.mutation_confidence and report_dir and os.path.isdir(report_dir):
            # Mutation-test the oracle for each execution-only (gap) function,
            # so each gap finding carries a confidence. Read the gap functions
            # from the round-0 gap report.
            from qallm.experiments.gap_confidence import score_gap_confidence_from_dir
            gap_funcs: list[str] = []
            for r in gap_rounds:
                if int(r.get("round", r.get("round_number", 0)) or 0) == 0:
                    gap_funcs = list(r.get("execution_only_functions", []) or [])
                    break
            gap_confidence = score_gap_confidence_from_dir(report_dir, gap_funcs)

        m = build_session_metrics(
            session_id=session_id,
            summary=summary,
            gap_rounds=gap_rounds,
            confirm_summary=confirm_summary,
            verify_summary=verify_summary,
        )
        row = {"input": str(input_path), "metrics": m.to_dict(), "error": None}
        if gap_confidence is not None:
            row["gap_confidence"] = gap_confidence
        return row
    except Exception as e:  # one bad notebook should not sink the run
        logger.warning("Input failed: %s: %s", input_path, e)
        logger.debug("Traceback for %s:\n%s", input_path, traceback.format_exc())
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
        inconclusive=d.get("inconclusive"),
        not_execution_testable=d.get("not_execution_testable"),
        incoherent_oracles_dropped=int(d.get("incoherent_oracles_dropped", 0) or 0),
        verified_fixed=d.get("verified_fixed"),
        not_fixed=d.get("not_fixed"),
        verified_fix_rate=d.get("verified_fix_rate"),
    )
