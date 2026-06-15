"""Tests for qallm.experiments.humaneval_runner.

The runner is exercised against synthetic problems and a mocked
orchestrator factory; no real LLM is invoked. The tests verify:

  * The runner iterates problems x strategies x models.
  * Results are appended to results.jsonl one per line.
  * Resumption skips combinations already recorded.
  * Errors are captured per problem and the loop continues.
  * The final report and aggregates are written to disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock


from qallm.experiments.humaneval_dataset import HumanEvalProblem
from qallm.experiments.humaneval_runner import (
    ExperimentConfig,
    run_experiment,
)


# ---------- helpers ----------


def _problem(task_id: str = "Python/0") -> HumanEvalProblem:
    return HumanEvalProblem(
        task_id=task_id,
        entry_point="add",
        declaration="def add(a, b):\n",
        prompt="def add(a, b):\n    \"\"\"Add two numbers.\"\"\"\n",
        canonical_solution="    return a + b\n",
        buggy_solution="    return a - b\n",
        bug_type="operator",
        failure_symptoms="",
        test="def check(candidate):\n    assert candidate(2, 3) == 5\n",
    )


def _config(tmp_path: Path, **overrides) -> ExperimentConfig:
    defaults = dict(
        output_dir=tmp_path / "out",
        models=["openai:stub"],
        strategies=["rl"],
        sample_size=None,
        seed=42,
        rounds=2,
        oracle="crash",
        judge_strategy="strict",
    )
    defaults.update(overrides)
    return ExperimentConfig(**defaults)


def _make_factory(*, summary_factory=None):
    """Return an orchestrator factory that produces a controllable mock.

    The orchestrator's only method called by the runner is ``run()``.
    """
    def factory(*, model, strategy, rounds, oracle, judge_strategy):
        orch = MagicMock()
        if summary_factory:
            orch.run.side_effect = summary_factory
        else:
            # Default summary: one session with a passing test against
            # canonical (so bug_detected is True for the synthetic problem).
            orch.run.return_value = _default_summary(model=model)
        # The reporter directory is referenced for lineage source readback;
        # an empty path means the metric fallback to buggy_full_source kicks in.
        orch.reporter = MagicMock()
        orch.reporter.report_dir = Path("/tmp/nonexistent")
        return orch
    return factory


def _default_summary(model: str = "openai:stub") -> dict:
    """A canonical-shape orchestrator summary the runner can parse."""
    return {
        "sessions": [{
            "function_name": "add",
            "rounds": [{
                "round_number": 1,
                "generated_test": {
                    "is_valid": True,
                    "test_code": "def check(candidate):\n    assert candidate(2, 3) == 5\n",
                },
            }],
            "final_bugs": 1,
            "final_coverage": 80.0,
        }],
        "rounds_per_function": 2,
        "cost": {"total_cost_usd": 0.01, "total_tokens": 1000},
        "tracks": {"add.py::0": {"lineage": [{"round_number": 1}]}},
        "report_dir": "",
        "model": model,
    }


# ---------- tests ----------


class TestBasicRunLoop:
    def test_runs_each_combination_once(self, tmp_path):
        problems = [_problem("Python/0"), _problem("Python/1")]
        config = _config(
            tmp_path, models=["m_a", "m_b"], strategies=["rl", "oneshot"],
        )
        factory = _make_factory()
        results = run_experiment(
            config, orchestrator_factory=factory, problems=problems,
        )
        # 2 problems * 2 strategies * 2 models = 8 combinations.
        assert len(results) == 8

    def test_writes_results_jsonl(self, tmp_path):
        problems = [_problem("Python/0")]
        config = _config(tmp_path, strategies=["rl"], models=["m"])
        run_experiment(
            config, orchestrator_factory=_make_factory(), problems=problems,
        )
        results_file = config.output_dir / "results.jsonl"
        assert results_file.exists()
        lines = [
            line for line in results_file.read_text().splitlines() if line.strip()
        ]
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["task_id"] == "Python/0"
        assert parsed["strategy"] == "rl"

    def test_writes_manifest_on_first_run(self, tmp_path):
        config = _config(tmp_path)
        run_experiment(
            config, orchestrator_factory=_make_factory(),
            problems=[_problem("Python/0")],
        )
        manifest = json.loads(
            (config.output_dir / "manifest.json").read_text()
        )
        assert manifest["seed"] == 42
        assert manifest["judge_strategy"] == "strict"
        assert "rl" in manifest["strategies"]

    def test_writes_final_report(self, tmp_path):
        config = _config(tmp_path)
        run_experiment(
            config, orchestrator_factory=_make_factory(),
            problems=[_problem("Python/0")],
        )
        report = config.output_dir / "report.md"
        assert report.exists()
        assert "HumanEvalFix experiment results" in report.read_text()

    def test_writes_aggregates_json(self, tmp_path):
        config = _config(tmp_path)
        run_experiment(
            config, orchestrator_factory=_make_factory(),
            problems=[_problem("Python/0")],
        )
        aggs_file = config.output_dir / "aggregates.json"
        assert aggs_file.exists()
        aggs = json.loads(aggs_file.read_text())
        assert len(aggs) == 1
        assert "bug_detection_rate" in aggs[0]


class TestResumability:
    def test_skips_combinations_already_in_jsonl(self, tmp_path):
        problems = [_problem("Python/0"), _problem("Python/1")]
        config = _config(tmp_path)

        # First run: complete both problems.
        factory = _make_factory()
        run_experiment(
            config, orchestrator_factory=factory, problems=problems,
        )
        # first_run_calls = sum(
        #     1 for c in [factory] if c
        # )  # Coverage check below.
        sum(
            1 for c in [factory] if c
        )  # Coverage check below.
        first_results_count = len([
            line for line in (config.output_dir / "results.jsonl")
                .read_text().splitlines() if line.strip()
        ])
        assert first_results_count == 2

        # Second run: the factory must not be called at all.
        factory2 = MagicMock(side_effect=AssertionError(
            "factory should not be called on resumed run"
        ))
        results = run_experiment(
            config, orchestrator_factory=factory2, problems=problems,
        )
        # Results returned still contain both, loaded from the jsonl.
        assert len(results) == 2

    def test_partial_resume_runs_only_missing(self, tmp_path):
        problems = [_problem("Python/0"), _problem("Python/1")]
        config = _config(tmp_path)

        # Pre-seed results.jsonl with only Python/0.
        config.output_dir.mkdir(parents=True)
        existing = {
            "task_id": "Python/0", "strategy": "rl", "model": "openai:stub",
            "bug_detected": True, "repair_successful": True,
            "rounds_run": 2, "total_bugs_reported": 1,
            "final_coverage": 80.0, "cost_usd": 0.01, "elapsed_seconds": 1.0,
            "error": None,
        }
        (config.output_dir / "results.jsonl").write_text(
            json.dumps(existing) + "\n"
        )

        call_count = {"n": 0}
        def factory(**kwargs):
            call_count["n"] += 1
            orch = MagicMock()
            orch.run.return_value = _default_summary()
            orch.reporter = MagicMock()
            orch.reporter.report_dir = Path("/tmp/x")
            return orch

        run_experiment(
            config, orchestrator_factory=factory, problems=problems,
        )
        # Only Python/1 should have triggered a factory call.
        assert call_count["n"] == 1


class TestErrorHandling:
    def test_orchestrator_exception_caught_and_recorded(self, tmp_path):
        problems = [_problem("Python/0"), _problem("Python/1")]
        config = _config(tmp_path)

        call_count = {"n": 0}
        def factory(**kwargs):
            call_count["n"] += 1
            orch = MagicMock()
            if call_count["n"] == 1:
                orch.run.side_effect = RuntimeError("simulated provider down")
            else:
                orch.run.return_value = _default_summary()
            orch.reporter = MagicMock()
            orch.reporter.report_dir = Path("/tmp/x")
            return orch

        results = run_experiment(
            config, orchestrator_factory=factory, problems=problems,
        )

        # Both problems produced a result; one with an error.
        assert len(results) == 2
        errored = [r for r in results if r.error is not None]
        assert len(errored) == 1
        assert "simulated provider down" in errored[0].error

    def test_errored_problem_skipped_on_resume_so_loop_completes(self, tmp_path):
        """A crashed run that we re-trigger should still complete.

        Even with errors, the JSONL line is written, so the resumption
        logic correctly skips that combination on the next run.
        """
        problems = [_problem("Python/0")]
        config = _config(tmp_path)

        def crashy_factory(**kwargs):
            orch = MagicMock()
            orch.run.side_effect = ValueError("kaboom")
            orch.reporter = MagicMock()
            orch.reporter.report_dir = Path("/tmp/x")
            return orch

        results = run_experiment(
            config, orchestrator_factory=crashy_factory, problems=problems,
        )
        assert len(results) == 1
        assert results[0].error is not None

        # Resume: the factory should not be called again.
        factory2 = MagicMock(side_effect=AssertionError(
            "must not be called"
        ))
        results2 = run_experiment(
            config, orchestrator_factory=factory2, problems=problems,
        )
        assert len(results2) == 1
        assert results2[0].error is not None  # Still recorded.


class TestProblemAggregation:
    def test_no_problems_does_not_crash(self, tmp_path):
        config = _config(tmp_path)
        results = run_experiment(
            config, orchestrator_factory=_make_factory(), problems=[],
        )
        assert results == []
        # Report still produced.
        assert (config.output_dir / "report.md").exists()

    def test_callback_invoked_per_problem(self, tmp_path):
        problems = [_problem("Python/0"), _problem("Python/1")]
        config = _config(tmp_path)
        callback_calls = []

        run_experiment(
            config,
            orchestrator_factory=_make_factory(),
            problems=problems,
            on_problem_complete=lambda r: callback_calls.append(r.task_id),
        )
        assert sorted(callback_calls) == ["Python/0", "Python/1"]
