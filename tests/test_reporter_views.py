"""Tests for qallm.utils.views.

Coverage:

  * render_markdown produces a non-empty string with all expected sections
    when given a populated summary dict.
  * render_html produces well-formed HTML with the same key information.
  * Both views handle missing or partial summaries gracefully.
  * Tracks with no lineage / no abandoned are handled.
  * Empty summary still renders without crashing.
  * write_views creates both files on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qallm.utils.views import render_html, render_markdown, write_views


# ---------- fixtures ----------


@pytest.fixture
def full_summary() -> dict:
    return {
        "source": "demo.py",
        "strategy": "rl",
        "judge_strategy": "lexicographic",
        "model": "gpt-4o-mini",
        "lifecycle_stage": "implementation",
        "rounds_accepted_total": 3,
        "rounds_abandoned_total": 1,
        "halt_reason": None,
        "cost": {"total_cost_usd": 0.0234, "total_tokens": 5000},
        "budget": {"elapsed_seconds": 12.4},
        "tracks": {
            "demo.py::-1": {
                "unit_id": "demo.py::-1",
                "lineage": [
                    {"round_number": 1, "judge_verdict": None},
                    {
                        "round_number": 3,
                        "judge_verdict": {
                            "outcome": "improvement",
                            "explanation": "Maintainability.mi rose from 60 to 75.",
                        },
                    },
                ],
                "abandoned": [
                    {
                        "round_number": 2,
                        "judge_verdict": {
                            "outcome": "regression",
                            "explanation": "Security.bandit_high increased from 0 to 2.",
                        },
                    },
                ],
            },
        },
        "sessions": [
            {
                "function_name": "add",
                "rounds": [{}],
                "final_coverage": 95.0,
                "final_bugs": 1,
            },
        ],
    }


@pytest.fixture
def empty_summary() -> dict:
    return {"source": "empty.py"}


# ---------- render_markdown ----------


class TestRenderMarkdown:
    def test_includes_header_and_metadata(self, full_summary):
        md = render_markdown(full_summary)
        assert "QALLM session report" in md
        assert "demo.py" in md
        assert "lexicographic" in md
        assert "gpt-4o-mini" in md

    def test_includes_totals(self, full_summary):
        md = render_markdown(full_summary)
        assert "3" in md  # rounds_accepted_total
        assert "0.0234" in md or "$0.02" in md
        assert "completed" in md  # halt_reason None -> "completed"

    def test_includes_per_unit_tables(self, full_summary):
        md = render_markdown(full_summary)
        assert "demo.py::-1" in md
        assert "improvement" in md
        assert "regression" in md or "Security.bandit_high" in md

    def test_handles_empty_summary(self, empty_summary):
        md = render_markdown(empty_summary)
        # Doesn't crash; still produces a header.
        assert "QALLM session report" in md
        assert "empty.py" in md

    def test_truncates_long_explanations(self):
        long_text = "a" * 500
        summary = {
            "source": "x.py",
            "tracks": {
                "x::-1": {
                    "lineage": [
                        {"round_number": 1, "judge_verdict": None},
                        {
                            "round_number": 2,
                            "judge_verdict": {
                                "outcome": "improvement",
                                "explanation": long_text,
                            },
                        },
                    ],
                    "abandoned": [],
                }
            },
        }
        md = render_markdown(summary)
        # The truncated form should end with "..." and be much shorter than 500.
        assert "..." in md
        # The full 500-char run should not appear.
        assert long_text not in md

    def test_escapes_pipe_in_table_cells(self):
        summary = {
            "source": "x.py",
            "tracks": {
                "x::-1": {
                    "lineage": [
                        {"round_number": 1, "judge_verdict": None},
                        {
                            "round_number": 2,
                            "judge_verdict": {
                                "outcome": "improvement",
                                "explanation": "uses pipe | here",
                            },
                        },
                    ],
                    "abandoned": [],
                }
            },
        }
        md = render_markdown(summary)
        # The pipe should be escaped so it doesn't break the table.
        assert "uses pipe \\| here" in md


# ---------- render_html ----------


class TestRenderHtml:
    def test_includes_doctype_and_basic_structure(self, full_summary):
        h = render_html(full_summary)
        assert "<!DOCTYPE html>" in h
        assert "<html" in h
        assert "</html>" in h
        assert "<head>" in h and "</head>" in h
        assert "<body>" in h and "</body>" in h

    def test_includes_inline_style(self, full_summary):
        h = render_html(full_summary)
        assert "<style>" in h
        assert "</style>" in h

    def test_escapes_html_in_source(self):
        # If a source path contained HTML-special characters, the output
        # must escape them so they don't render as tags.
        summary = {"source": "<script>alert(1)</script>"}
        h = render_html(summary)
        assert "<script>alert" not in h
        assert "&lt;script&gt;" in h

    def test_includes_outcome_classes(self, full_summary):
        h = render_html(full_summary)
        # The CSS classes used for colour-coding are present in the output.
        assert "improvement" in h
        assert "regression" in h

    def test_handles_empty_summary(self, empty_summary):
        h = render_html(empty_summary)
        assert "<!DOCTYPE html>" in h
        assert "empty.py" in h

    def test_handles_track_with_no_abandoned_list(self):
        summary = {
            "source": "x.py",
            "tracks": {
                "x::-1": {
                    "lineage": [{"round_number": 1, "judge_verdict": None}],
                    "abandoned": [],
                }
            },
        }
        # Should not crash, should not include the "Abandoned variants" header.
        h = render_html(summary)
        assert "Abandoned variants" not in h


# ---------- write_views ----------


class TestWriteViews:
    def test_writes_both_files(self, full_summary, tmp_path: Path):
        md_path, html_path = write_views(full_summary, tmp_path)
        assert md_path.exists()
        assert html_path.exists()
        assert md_path.name == "report.md"
        assert html_path.name == "report.html"

    def test_files_contain_rendered_content(self, full_summary, tmp_path: Path):
        md_path, html_path = write_views(full_summary, tmp_path)
        assert "QALLM session report" in md_path.read_text()
        assert "<!DOCTYPE html>" in html_path.read_text()
