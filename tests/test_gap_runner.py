"""Tests for the verification-gap batch runner."""

import json
import os
from pathlib import Path

from qallm.experiments.gap_runner import (
    GapExperimentConfig,
    run_gap_experiment,
    _discover_inputs,
)


def _make_dataset(tmp_path: Path, names):
    d = tmp_path / "data"
    d.mkdir()
    for n in names:
        (d / n).write_text("# notebook placeholder\n")
    return d


def _fake_summary(report_dir, gap):
    """A fake orchestrator that writes gap artefacts and returns a summary."""
    os.makedirs(os.path.join(report_dir, "lineage", "round_0", "unit"), exist_ok=True)
    unit = os.path.join(report_dir, "lineage", "round_0", "unit")
    Path(os.path.join(unit, "source.py")).write_text(gap["source"])
    Path(os.path.join(unit, "static.json")).write_text(json.dumps(gap["static"]))
    Path(os.path.join(unit, "verification.json")).write_text(json.dumps(gap["verification"]))
    return {
        "report_dir": report_dir,
        "model": "fedllm/gpt-oss-120b",
        "oracle": "crash",
        "rounds_per_function": 5,
        "units_analyzed": 1,
        "functions_verified": 1,
        "cost": {"total_cost_usd": 0.0, "total_tokens": 1234},
    }


class _FakeOrch:
    def __init__(self, report_root, idx):
        self._report_root = report_root
        self._idx = idx

    def run(self, source):
        rd = os.path.join(self._report_root, f"session_{self._idx}")
        # One execution-only bug (function f fails), no static finding: a gap.
        gap = {
            "source": "def f(x):\n    return x + 1\n",
            "static": [],
            "verification": [
                {"function": "f", "rounds": [
                    {"execution": {"passed": 0, "failed": 1, "errors": 0}}]},
            ],
        }
        return _fake_summary(rd, gap)


def test_discover_inputs_sorted(tmp_path):
    d = _make_dataset(tmp_path, ["b.ipynb", "a.ipynb", "c.txt"])
    found = _discover_inputs(d, "*.ipynb")
    assert [p.name for p in found] == ["a.ipynb", "b.ipynb"]


def test_run_produces_aggregate_and_files(tmp_path):
    d = _make_dataset(tmp_path, ["n1.ipynb", "n2.ipynb"])
    out = tmp_path / "out"
    report_root = tmp_path / "reports"
    report_root.mkdir()

    counter = {"i": 0}

    def factory(config):
        counter["i"] += 1
        return _FakeOrch(str(report_root), counter["i"])

    config = GapExperimentConfig(dataset_dir=d, output_dir=out)
    result = run_gap_experiment(config, orchestrator_factory=factory)

    # Two sessions, each a pure gap (1 execution-only, 0 confirmed) -> rate 1.0
    assert len(result.per_session) == 2
    assert result.aggregate["verification_gap_rate"] == 1.0
    assert (out / "results.jsonl").exists()
    assert (out / "aggregate.json").exists()
    assert (out / "metrics.csv").exists()
    assert (out / "manifest.json").exists()


def test_resumability_skips_completed(tmp_path):
    d = _make_dataset(tmp_path, ["n1.ipynb", "n2.ipynb"])
    out = tmp_path / "out"
    report_root = tmp_path / "reports"
    report_root.mkdir()
    counter = {"i": 0}

    def factory(config):
        counter["i"] += 1
        return _FakeOrch(str(report_root), counter["i"])

    config = GapExperimentConfig(dataset_dir=d, output_dir=out)
    run_gap_experiment(config, orchestrator_factory=factory)
    runs_after_first = counter["i"]
    # Second invocation should skip both completed inputs.
    run_gap_experiment(config, orchestrator_factory=factory)
    assert counter["i"] == runs_after_first  # no new orchestrator runs


def test_error_isolated_per_input(tmp_path):
    d = _make_dataset(tmp_path, ["good.ipynb", "bad.ipynb"])
    out = tmp_path / "out"
    report_root = tmp_path / "reports"
    report_root.mkdir()

    class Factory:
        def __call__(self, config):
            # Decide good vs bad by the input is not available here, so use a
            # counter keyed to insertion; inputs are processed sorted, so
            # "bad.ipynb" (alphabetically first) is run first.
            self.n = getattr(self, "n", 0) + 1
            if self.n == 1:
                class Boom:
                    def run(self, source):
                        raise RuntimeError("kernel exploded")
                return Boom()
            return _FakeOrch(str(report_root), 1)

    config = GapExperimentConfig(dataset_dir=d, output_dir=out)
    result = run_gap_experiment(config, orchestrator_factory=Factory())
    assert len(result.per_session) == 1     # the good one
    assert len(result.errors) == 1          # the bad one, isolated
    assert "kernel exploded" in result.errors[0]["error"]
