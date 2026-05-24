"""Tests for qallm.experiments.humaneval_report.

Verifies the markdown output contains the headline numbers, the
manifest, the per-problem appendix, and degrades cleanly when fields
are missing.
"""

from __future__ import annotations

from qallm.experiments.humaneval_metrics import (
    AggregateResult,
    ProblemResult,
)
from qallm.experiments.humaneval_report import render_markdown


def _result(**kwargs) -> ProblemResult:
    defaults = dict(
        task_id="Python/0", strategy="rl", model="openai:gpt-4o-mini",
        bug_detected=True, repair_successful=True,
        rounds_run=3, total_bugs_reported=1,
        final_coverage=85.0, cost_usd=0.02, elapsed_seconds=12.5,
        error=None,
    )
    defaults.update(kwargs)
    return ProblemResult(**defaults)


def _agg(**kwargs) -> AggregateResult:
    defaults = dict(
        strategy="rl", model="openai:gpt-4o-mini",
        n_problems=10, n_bug_detected=8, n_repair_successful=7,
        n_errored=0, mean_rounds=3.2, mean_cost_usd=0.025,
        mean_elapsed_seconds=15.0,
    )
    defaults.update(kwargs)
    return AggregateResult(**defaults)


def _manifest() -> dict:
    return {
        "models": ["openai:gpt-4o-mini", "ollama:gemma3:4b"],
        "strategies": ["rl", "oneshot", "hypothesis"],
        "sample_size": None,
        "seed": 42,
        "rounds": 5,
        "oracle": "crash",
        "judge_strategy": "lexicographic",
    }


class TestReportStructure:
    def test_has_headline_section(self):
        md = render_markdown(
            manifest=_manifest(),
            aggregates=[_agg()],
            wilcoxon_results=[],
            problem_results=[_result()],
        )
        assert "# HumanEvalFix experiment results" in md
        assert "## Headline results" in md
        assert "## Run manifest" in md
        assert "## Per-problem detail" in md

    def test_renders_aggregates_as_table(self):
        md = render_markdown(
            manifest=_manifest(),
            aggregates=[_agg(strategy="rl", n_bug_detected=8)],
            wilcoxon_results=[],
            problem_results=[],
        )
        assert "| Strategy | Model | N |" in md
        assert "rl" in md
        assert "8/10" in md  # detected count / valid

    def test_manifest_keys_appear(self):
        md = render_markdown(
            manifest=_manifest(),
            aggregates=[],
            wilcoxon_results=[],
            problem_results=[],
        )
        assert "seed" in md
        assert "42" in md
        assert "lexicographic" in md


class TestErrorHandling:
    def test_errored_results_appear_in_appendix(self):
        results = [
            _result(task_id="Python/0"),
            _result(task_id="Python/1", error="OllamaConnectionError: ..."),
        ]
        md = render_markdown(
            manifest=_manifest(),
            aggregates=[_agg(n_problems=2, n_errored=1)],
            wilcoxon_results=[],
            problem_results=results,
        )
        assert "## Errored runs" in md
        assert "OllamaConnectionError" in md
        assert "Python/1" in md

    def test_errored_runs_show_err_in_table(self):
        results = [_result(task_id="Python/0", error="boom")]
        md = render_markdown(
            manifest=_manifest(),
            aggregates=[_agg(n_problems=1, n_errored=1)],
            wilcoxon_results=[],
            problem_results=results,
        )
        # The per-problem table uses "err" placeholders for errored rows.
        assert "| err |" in md


class TestWilcoxonSection:
    def test_wilcoxon_table_appears_when_present(self):
        md = render_markdown(
            manifest=_manifest(),
            aggregates=[_agg()],
            wilcoxon_results=[{
                "a": "rl", "b": "oneshot", "model": "openai:gpt-4o-mini",
                "metric": "bug_detected", "n": 30,
                "statistic": 12.5, "pvalue": 0.003,
            }],
            problem_results=[],
        )
        assert "## Pairwise significance" in md
        assert "rl vs oneshot" in md
        assert "0.003" in md or "0.0030" in md

    def test_wilcoxon_section_omitted_when_empty(self):
        md = render_markdown(
            manifest=_manifest(),
            aggregates=[_agg()],
            wilcoxon_results=[],
            problem_results=[],
        )
        assert "## Pairwise significance" not in md

    def test_wilcoxon_handles_missing_statistic(self):
        md = render_markdown(
            manifest=_manifest(),
            aggregates=[_agg()],
            wilcoxon_results=[{
                "a": "rl", "b": "oneshot", "model": "m",
                "metric": "bug_detected", "n": 30,
                "statistic": None, "pvalue": None,
                "note": "all differences zero",
            }],
            problem_results=[],
        )
        assert "n/a" in md or "all differences zero" in md


class TestEmptyAggregates:
    def test_empty_aggregates_does_not_crash(self):
        md = render_markdown(
            manifest=_manifest(),
            aggregates=[],
            wilcoxon_results=[],
            problem_results=[],
        )
        # Still has a header section, just no rows.
        assert "# HumanEvalFix experiment results" in md
