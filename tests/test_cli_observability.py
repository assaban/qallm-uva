"""Tests for the CLI observability presenter (pure formatting)."""

import json
import os
import tempfile

from qallm.cli_observability import (
    build_observability_report,
    collect_round_improvements,
    format_improvement,
    format_transcript_summary,
)


def test_format_transcript_summary_empty():
    assert format_transcript_summary([]) == ["  (no LLM calls recorded)"]


def test_format_transcript_summary_one_call():
    recs = [{
        "context": {"round_number": 2, "role": "testgen", "function": "foo"},
        "input_tokens": 100, "output_tokens": 20,
        "cost_usd": 0.0012, "latency_ms": 450.0,
    }]
    lines = format_transcript_summary(recs)
    assert len(lines) == 1
    assert "r2 testgen foo" in lines[0]
    assert "100+20tok" in lines[0]


def test_format_improvement_shows_transition():
    rep = {
        "headline": "Round 1 ACCEPTED",
        "dimensions": [{
            "dimension": "Security", "net": "improved",
            "indicators": [{
                "name": "bandit_high", "direction": "improved",
                "parent_measured": 3.0, "variant_measured": 0.0,
                "status_transition": "FAIL->PASS",
            }],
        }],
    }
    text = "\n".join(format_improvement(rep))
    assert "Round 1 ACCEPTED" in text
    assert "FAIL->PASS" in text
    assert "+ bandit_high" in text


def test_collect_round_improvements_reads_artefacts():
    with tempfile.TemporaryDirectory() as d:
        unit_dir = os.path.join(d, "lineage", "round_1", "file.py__foo")
        os.makedirs(unit_dir)
        with open(os.path.join(unit_dir, "improvement.json"), "w") as fh:
            json.dump({"headline": "h", "dimensions": []}, fh)
        got = collect_round_improvements(d)
        assert len(got) == 1
        assert got[0][0] == 1  # round number


def test_build_report_points_at_artefacts():
    with tempfile.TemporaryDirectory() as d:
        text = build_observability_report([], d, show_transcript=False)
        assert "Improvement audit" in text
        assert d in text  # points the user at the on-disk artefacts


def test_build_report_with_transcript_lists_calls():
    recs = [{
        "context": {"round_number": 1, "role": "repair"},
        "input_tokens": 50, "output_tokens": 10,
        "cost_usd": 0.0, "latency_ms": 100.0,
    }]
    with tempfile.TemporaryDirectory() as d:
        text = build_observability_report(recs, d, show_transcript=True)
        assert "LLM calls" in text
        assert "r1 repair" in text
