"""HumanEvalFix experiment runner.

Drives the QALLM pipeline against each (problem, strategy, model) triple,
computes the bug-detection and repair-success outcomes, and persists
results incrementally so a crash does not lose work.

Design choices
--------------

* **One subprocess per QALLM run.** Each problem's QALLM run is isolated
  via the orchestrator's own machinery, but we still wrap the call in
  try/except so a single failure does not abort the experiment.

* **Resumable.** Results are appended to a JSONL file as they complete.
  On startup, the runner reads existing results and skips combinations
  already recorded. This means re-running the same command after a crash
  picks up where it stopped.

* **Deterministic enough.** True determinism is impossible with real LLMs
  (temperature, server-side variation). We record the random seed used
  for sampling and the model/strategy/parameters used for each run, so a
  reviewer can re-run with the same parameters and compare distributions.

* **No automated full-run from tests.** The actual experiment costs money
  and time; the test suite exercises the *plumbing* with mocked
  collaborators, never triggering a real LLM call.
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from qallm.experiments.humaneval_dataset import HumanEvalProblem, load_humanevalfix
from qallm.experiments.humaneval_metrics import (
    ProblemResult,
    aggregate,
    bug_was_detected,
    repair_was_successful,
    wilcoxon_pairs,
)
from qallm.experiments.humaneval_report import render_markdown

logger = logging.getLogger(__name__)


@dataclass
class ExperimentConfig:
    """Parameters for one full experiment run."""

    output_dir: Path
    models: list[str]            # e.g. ["openai:gpt-4o-mini", "ollama:gemma3:4b"]
    strategies: list[str]        # subset of ["rl", "oneshot", "hypothesis"]
    sample_size: Optional[int]   # None for all 164
    seed: int                    # sampling seed
    rounds: int                  # QALLM rounds per run
    oracle: str                  # crash / property / metamorphic
    judge_strategy: str          # strict / lexicographic / model
    workers: int = 1             # parallel worker threads (1 = serial)

    def to_manifest(self) -> dict:
        return {
            "models": self.models,
            "strategies": self.strategies,
            "sample_size": self.sample_size,
            "seed": self.seed,
            "rounds": self.rounds,
            "oracle": self.oracle,
            "judge_strategy": self.judge_strategy,
            "workers": self.workers,
            "output_dir": str(self.output_dir),
        }


# ---------- the main loop ----------


def run_experiment(
    config: ExperimentConfig,
    *,
    orchestrator_factory: Optional[Callable[..., Any]] = None,
    problems: Optional[list[HumanEvalProblem]] = None,
    on_problem_complete: Optional[Callable[[ProblemResult], None]] = None,
) -> list[ProblemResult]:
    """Run the experiment to completion and return all results.

    Args:
        config: experiment parameters.
        orchestrator_factory: factory that builds a QALLMOrchestrator
            given (model, strategy, rounds, oracle, judge_strategy).
            Defaults to the real orchestrator constructor; tests inject
            a mock here.
        problems: pre-loaded problems. If None, loads via the dataset
            module using config.sample_size and config.seed.
        on_problem_complete: callback after each problem result is saved.
            Useful for live progress bars or notifications.

    Returns:
        All ProblemResult entries, in the order they completed.
    """
    config.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = config.output_dir / "manifest.json"
    results_path = config.output_dir / "results.jsonl"

    if not manifest_path.exists():
        manifest_path.write_text(
            json.dumps(config.to_manifest(), indent=2), encoding="utf-8"
        )

    # Resumption: read prior results to skip done combinations.
    completed_keys: set[tuple[str, str, str]] = set()
    results: list[ProblemResult] = []
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                results.append(ProblemResult(**d))
                completed_keys.add((d["task_id"], d["strategy"], d["model"]))
            except Exception as e:
                logger.warning("Skipping corrupt result line: %s", e)
        logger.info(
            "Resumed with %d existing results; skipping done combinations.",
            len(completed_keys),
        )

    if problems is None:
        problems = load_humanevalfix(
            sample_size=config.sample_size, seed=config.seed
        )

    if orchestrator_factory is None:
        orchestrator_factory = _default_orchestrator_factory

    total = len(problems) * len(config.strategies) * len(config.models)
    done = len(completed_keys)
    logger.info(
        "Running %d combinations total (%d already done, %d to run)",
        total, done, total - done,
    )

    # Build the list of combinations still to run (resumable: skip done ones).
    # Order problem -> strategy -> model so a serial run still groups the report
    # by problem, which is what most readers want.
    pending: list[tuple[HumanEvalProblem, str, str]] = []
    for problem in problems:
        for strategy in config.strategies:
            for model in config.models:
                key = (problem.task_id, strategy, model)
                if key not in completed_keys:
                    pending.append((problem, strategy, model))

    # Writing to the JSONL, appending to results, and invoking the progress
    # callback must be serialised even when workers run in parallel; a lock
    # around just those steps keeps the file and the in-memory list consistent
    # while the expensive _run_one work (LLM calls, execution) stays concurrent.
    import threading
    write_lock = threading.Lock()

    def _record(result: ProblemResult, out) -> None:
        with write_lock:
            out.write(json.dumps(result.to_dict()) + "\n")
            out.flush()
            results.append(result)
            if on_problem_complete is not None:
                on_problem_complete(result)

    def _run_combo(problem, strategy, model) -> ProblemResult:
        logger.info("Running %s [strategy=%s, model=%s]",
                    problem.task_id, strategy, model)
        return _run_one(
            problem=problem, strategy=strategy, model=model,
            config=config, orchestrator_factory=orchestrator_factory,
        )

    workers = max(1, int(getattr(config, "workers", 1) or 1))
    with results_path.open("a", encoding="utf-8") as out:
        if workers == 1:
            # Serial path unchanged, so single-worker behaviour is identical.
            for problem, strategy, model in pending:
                _record(_run_combo(problem, strategy, model), out)
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_run_combo, p, s, m): (p, s, m)
                    for (p, s, m) in pending
                }
                for fut in as_completed(futures):
                    p, s, m = futures[fut]
                    try:
                        result = fut.result()
                    except Exception as exc:  # a worker crashed; record it
                        logger.exception("Worker failed for %s [%s, %s]",
                                         p.task_id, s, m)
                        result = _error_result(p, s, m, exc)
                    _record(result, out)

    # Final aggregation and report.
    aggs = aggregate(results)
    wilcoxon = wilcoxon_pairs(results, metric="bug_detected")
    wilcoxon += wilcoxon_pairs(results, metric="repair_successful")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report_md = render_markdown(
        manifest=manifest,
        aggregates=aggs,
        wilcoxon_results=wilcoxon,
        problem_results=results,
    )
    (config.output_dir / "report.md").write_text(report_md, encoding="utf-8")
    (config.output_dir / "aggregates.json").write_text(
        json.dumps([a.to_dict() for a in aggs], indent=2),
        encoding="utf-8",
    )
    return results


# ---------- single-problem driver ----------


def _run_one(
    *,
    problem: HumanEvalProblem,
    strategy: str,
    model: str,
    config: ExperimentConfig,
    orchestrator_factory: Callable[..., Any],
) -> ProblemResult:
    """Run QALLM on one problem and compute its metrics.

    All exceptions are caught and recorded as the ``error`` field; a
    crash on one problem must not abort the whole experiment.
    """
    start = time.time()
    try:
        orch = orchestrator_factory(
            model=model,
            strategy=strategy,
            rounds=config.rounds,
            oracle=config.oracle,
            judge_strategy=config.judge_strategy,
        )
        # Write the buggy program to a temp file under the orchestrator's
        # working area, then call orch.run on it.
        import tempfile
        with tempfile.TemporaryDirectory(prefix=f"heval_{problem.task_id.replace('/', '_')}_") as td:
            src = Path(td) / f"{problem.entry_point}.py"
            src.write_text(problem.buggy_full_source, encoding="utf-8")
            summary = orch.run(str(src))

        # Extract what we need.
        sessions = summary.get("sessions", [])
        total_bugs = sum(s.get("final_bugs", 0) for s in sessions)
        coverages = [s.get("final_coverage") for s in sessions
                     if s.get("final_coverage") is not None]
        final_coverage = sum(coverages) / len(coverages) if coverages else 0.0
        cost = (summary.get("cost") or {}).get("total_cost_usd", 0.0)

        # The repaired source is the head of the unit's lineage. There's
        # one code unit per file; pick it.
        tracks = summary.get("tracks", {})
        repaired_source = problem.buggy_full_source  # fallback
        if tracks:
            # Find the single track and its head.
            track = next(iter(tracks.values()))
            lineage = track.get("lineage", [])
            if lineage:
                # Locate the actual source on disk from the reporter dir.
                # We store source.py in the latest lineage round directory.
                head_round = lineage[-1].get("round_number")
                if head_round is not None:
                    repaired_source = _read_lineage_source(
                        summary.get("report_dir") or "",
                        head_round,
                    ) or repaired_source

        # Extract a sample of QALLM-generated tests for the
        # bug-detection check. We use the first session's last valid test.
        qallm_test_code = _first_valid_qallm_test(sessions) or ""

        elapsed = time.time() - start

        # Compute the two definitions.
        detected = False
        if qallm_test_code:
            detected = bug_was_detected(
                qallm_test_code=qallm_test_code,
                buggy_source=problem.buggy_full_source,
                canonical_source=problem.canonical_full_source,
                entry_point=problem.entry_point,
            )
        repaired_ok = repair_was_successful(
            repaired_source=repaired_source,
            dataset_test=problem.test,
            entry_point=problem.entry_point,
        )

        return ProblemResult(
            task_id=problem.task_id,
            strategy=strategy,
            model=model,
            bug_detected=detected,
            repair_successful=repaired_ok,
            rounds_run=int(summary.get("rounds_per_function", config.rounds)),
            total_bugs_reported=total_bugs,
            final_coverage=final_coverage,
            cost_usd=float(cost),
            elapsed_seconds=elapsed,
        )

    except Exception as e:
        elapsed = time.time() - start
        tb = traceback.format_exc(limit=3)
        logger.exception("Problem %s failed", problem.task_id)
        return ProblemResult(
            task_id=problem.task_id,
            strategy=strategy,
            model=model,
            bug_detected=False,
            repair_successful=False,
            rounds_run=0,
            total_bugs_reported=0,
            final_coverage=0.0,
            cost_usd=0.0,
            elapsed_seconds=elapsed,
            error=f"{type(e).__name__}: {e}\n{tb}",
        )


# ---------- helpers ----------


def _error_result(problem: "HumanEvalProblem", strategy: str, model: str,
                  exc: BaseException) -> "ProblemResult":
    """Build an error ProblemResult for a combination that crashed at the
    worker boundary. _run_one catches its own exceptions, so this is a
    defensive fallback for the parallel path only."""
    return ProblemResult(
        task_id=problem.task_id,
        strategy=strategy,
        model=model,
        bug_detected=False,
        repair_successful=False,
        rounds_run=0,
        total_bugs_reported=0,
        final_coverage=0.0,
        cost_usd=0.0,
        elapsed_seconds=0.0,
        error=f"{type(exc).__name__}: {exc}",
    )


def _default_orchestrator_factory(
    *,
    model: str,
    strategy: str,
    rounds: int,
    oracle: str,
    judge_strategy: str,
    reporter_dir: str | None = None,
):
    """Build a real QALLMOrchestrator from a model id like ``openai:gpt-4o-mini``."""
    from qallm.orchestrator import QALLMOrchestrator
    from qallm.config import settings
    llm_type, _, model_name = model.partition(":")
    return QALLMOrchestrator(
        llm_type=llm_type,
        model_name=model_name or None,
        strategy=strategy,
        rounds=rounds,
        oracle=oracle,
        judge_strategy=judge_strategy,
        # Experiments write reporter artefacts to a separate dir (defaulting to
        # the experiment reporter dir), never the Web-UI session directory.
        reporter_dir=reporter_dir or settings.QALLM_EXPERIMENT_REPORTER_DIR,
    )


def _first_valid_qallm_test(sessions: list[dict]) -> Optional[str]:
    """Find the first valid test in any session's rounds."""
    for s in sessions:
        rounds = s.get("rounds", [])
        # Iterate from the last round backwards: later tests are usually
        # better than earlier ones under RL.
        for r in reversed(rounds):
            gt = r.get("generated_test", {})
            if gt.get("is_valid") and gt.get("test_code"):
                return gt["test_code"]
    return None


def _read_lineage_source(report_dir: str, round_number: int) -> Optional[str]:
    """Read source.py from a lineage round directory.

    The reporter saves each round's source under
    ``lineage/round_NN/<unit_segment>/source.py``. We find the first such
    file under the round directory.
    """
    if not report_dir:
        return None
    round_dir = Path(report_dir) / "lineage" / f"round_{round_number:02d}"
    if not round_dir.exists():
        return None
    sources = list(round_dir.glob("*/source.py"))
    if not sources:
        return None
    try:
        return sources[0].read_text(encoding="utf-8")
    except OSError:
        return None
