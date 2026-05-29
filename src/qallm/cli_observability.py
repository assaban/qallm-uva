"""Render observability data for the CLI.

The web UI shows, per round and per method, which indicators moved and the
prompts sent to the model. This module gives the CLI the same insight as
plain text. It reads the orchestrator's in-memory transcript and the
per-round improvement.json artefacts the reporter wrote, and formats them.

Kept separate from run_qallm.py so the formatting is unit-testable without
running a pipeline. Pure functions: each takes data, returns lines.
"""

from __future__ import annotations

import json
import os
from typing import Any


def format_transcript_summary(records: list[dict[str, Any]]) -> list[str]:
    """One line per LLM call: round, role, function, tokens, cost, latency.

    Bodies (prompts/responses) are not printed here; they can be large.
    Point the reader at the on-disk transcript.json for full text.
    """
    if not records:
        return ["  (no LLM calls recorded)"]
    lines = []
    for r in records:
        ctx = r.get("context", {})
        rnd = ctx.get("round_number", "?")
        role = ctx.get("role") or ctx.get("stage") or "call"
        fn = ctx.get("function")
        fn_str = f" {fn}" if fn else ""
        toks = f"{r.get('input_tokens', 0)}+{r.get('output_tokens', 0)}tok"
        cost = r.get("cost_usd", 0.0)
        lat = r.get("latency_ms", 0.0)
        err = " ERROR" if r.get("error") else ""
        lines.append(
            f"  r{rnd} {role}{fn_str}: {toks}, ${cost:.4f}, {lat:.0f}ms{err}"
        )
    return lines


def _direction_glyph(direction: str) -> str:
    return {
        "improved": "+", "appeared": "+",
        "regressed": "-", "disappeared": "-",
        "unchanged": "=",
    }.get(direction, "?")


def format_improvement(report: dict[str, Any]) -> list[str]:
    """Render one round's improvement report as indented text."""
    lines = [f"  {report.get('headline', '(no headline)')}"]
    for dim in report.get("dimensions", []):
        net = dim.get("net", "")
        lines.append(f"    {dim.get('dimension', '?')} [{net}]")
        for ind in dim.get("indicators", []):
            g = _direction_glyph(ind.get("direction", ""))
            pm = ind.get("parent_measured")
            vm = ind.get("variant_measured")
            trans = ind.get("status_transition", "")
            lines.append(
                f"      {g} {ind.get('name', '?')}: {pm} -> {vm} ({trans})"
            )
    return lines


def collect_round_improvements(report_dir: str) -> list[tuple[int, str, dict]]:
    """Read every improvement.json under a report dir.

    Returns (round_number, unit_segment, report_dict) tuples, ordered by
    round then unit. Walks both lineage/ and abandoned/ buckets.
    """
    out: list[tuple[int, str, dict]] = []
    if not report_dir or not os.path.isdir(report_dir):
        return out
    for bucket in ("lineage", "abandoned"):
        bucket_dir = os.path.join(report_dir, bucket)
        if not os.path.isdir(bucket_dir):
            continue
        for round_name in sorted(os.listdir(bucket_dir)):
            round_path = os.path.join(bucket_dir, round_name)
            if not os.path.isdir(round_path):
                continue
            try:
                rnd = int(round_name.replace("round_", ""))
            except ValueError:
                continue
            for unit_seg in sorted(os.listdir(round_path)):
                imp_path = os.path.join(round_path, unit_seg, "improvement.json")
                if os.path.isfile(imp_path):
                    try:
                        with open(imp_path, encoding="utf-8") as fh:
                            out.append((rnd, unit_seg, json.load(fh)))
                    except (OSError, json.JSONDecodeError):
                        pass
    out.sort(key=lambda t: (t[0], t[1]))
    return out


def build_observability_report(
    transcript_records: list[dict[str, Any]],
    report_dir: str,
    *,
    show_transcript: bool = False,
) -> str:
    """Build the full CLI observability block as a single string.

    Always shows the per-round improvement audit and points at the on-disk
    artefacts. With ``show_transcript`` it also lists every LLM call.
    """
    lines: list[str] = []
    lines.append("Improvement audit (per round, per method)")
    lines.append("-" * 60)

    improvements = collect_round_improvements(report_dir)
    if not improvements:
        lines.append("  (no per-round improvement artefacts found)")
    else:
        last_round = None
        for rnd, unit_seg, report in improvements:
            if rnd != last_round:
                label = "Baseline" if rnd == 0 else f"Round {rnd}"
                lines.append(f"\n{label}:")
                last_round = rnd
            lines.append(f"  {unit_seg}")
            lines.extend(format_improvement(report))

    if show_transcript:
        lines.append("")
        lines.append("LLM calls (use transcript.json for full prompt text)")
        lines.append("-" * 60)
        lines.extend(format_transcript_summary(transcript_records))

    if report_dir:
        lines.append("")
        lines.append(f"Full artefacts on disk: {report_dir}")
        lines.append("  Per round: static.json, verification.json, profile.json,")
        lines.append("  judge.json, improvement.json, transcript.json")

    return "\n".join(lines)
