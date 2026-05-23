"""Human-readable views over ``summary.json``.

Per workflow design v3 section 10.1, the canonical artefact is the
machine-readable ``summary.json``; ``report.md`` and ``report.html`` are
derived views for human readers. This module renders both.

Design choices
--------------

* No external templating library. The HTML uses inline CSS and a small
  string-template approach. The Markdown is built with plain string joins.
  Both are intentionally readable so the methodology chapter can quote them.

* Both views read the same dict. A caller can build them from an
  in-memory ``summary`` dict (the orchestrator's output) or from a file
  on disk (post-hoc analysis).

* Views show: session metadata, per-unit lineage with per-round outcome,
  judge verdict explanations, the abandoned variants count, and budget
  totals. They do NOT inline the full source code; they link to it under
  ``lineage/round_N/source.py``.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def render_markdown(summary: dict[str, Any]) -> str:
    """Render a session summary as a Markdown report."""
    lines: list[str] = []

    # Header
    lines.append(f"# QALLM session report")
    lines.append("")
    lines.append(f"**Source**: `{summary.get('source', 'unknown')}`")
    lines.append(f"**Strategy**: {summary.get('strategy', '?')}  ")
    lines.append(f"**Judge strategy**: {summary.get('judge_strategy', '?')}  ")
    lines.append(f"**Model**: {summary.get('model', '?')}  ")
    lines.append(f"**Lifecycle stage**: {summary.get('lifecycle_stage', '?')}  ")
    lines.append("")

    # Totals
    lines.append("## Totals")
    lines.append("")
    accepted = summary.get("rounds_accepted_total", 0)
    abandoned = summary.get("rounds_abandoned_total", 0)
    lines.append(f"- Rounds accepted (across all units): **{accepted}**")
    lines.append(f"- Rounds abandoned: **{abandoned}**")
    halt = summary.get("halt_reason") or "completed"
    lines.append(f"- Halt reason: **{halt}**")
    cost = summary.get("cost", {})
    if cost:
        usd = cost.get("total_cost_usd", 0.0)
        tokens = cost.get("total_tokens", 0)
        lines.append(f"- Cost: **${usd:.4f}** USD, {tokens} tokens")
    budget = summary.get("budget", {})
    if budget:
        elapsed = budget.get("elapsed_seconds", 0)
        lines.append(f"- Wall-clock: **{elapsed:.1f}s**")
    lines.append("")

    # Per-unit tracks
    tracks = summary.get("tracks", {})
    if tracks:
        lines.append("## Per-unit results")
        lines.append("")
        for unit_id, track in tracks.items():
            lines.append(f"### `{unit_id}`")
            lines.append("")
            lineage = track.get("lineage", [])
            abandoned_list = track.get("abandoned", [])
            lines.append(
                f"_Lineage_: **{len(lineage)}** accepted variant(s); "
                f"_Abandoned_: **{len(abandoned_list)}**."
            )
            lines.append("")

            if lineage:
                lines.append("| Round | Outcome | Explanation |")
                lines.append("|-------|---------|-------------|")
                for entry in lineage:
                    rn = entry.get("round_number", "?")
                    jv = entry.get("judge_verdict")
                    if jv is None:
                        outcome = "accepted (round 1)"
                        expl = "_unconditional_"
                    else:
                        outcome = jv.get("outcome", "?")
                        expl = _truncate(jv.get("explanation", ""), 120)
                    lines.append(f"| {rn} | {outcome} | {_md_escape(expl)} |")
                lines.append("")

            if abandoned_list:
                lines.append("**Abandoned variants:**")
                lines.append("")
                lines.append("| Round | Reason |")
                lines.append("|-------|--------|")
                for entry in abandoned_list:
                    rn = entry.get("round_number", "?")
                    jv = entry.get("judge_verdict") or {}
                    expl = _truncate(jv.get("explanation", ""), 120)
                    lines.append(f"| {rn} | {_md_escape(expl)} |")
                lines.append("")

    # Sessions summary (verification)
    sessions = summary.get("sessions", [])
    if sessions:
        lines.append("## Verification sessions")
        lines.append("")
        lines.append("| Function | Rounds | Coverage | Bugs found |")
        lines.append("|----------|--------|----------|------------|")
        for s in sessions:
            fn = s.get("function") or s.get("function_name", "?")
            r = len(s.get("rounds", [])) if isinstance(s.get("rounds"), list) else "?"
            cov = s.get("final_coverage")
            cov_s = f"{cov:.1f}%" if isinstance(cov, (int, float)) else "n/a"
            bugs = s.get("final_bugs", 0)
            lines.append(f"| `{fn}` | {r} | {cov_s} | {bugs} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("Generated from `summary.json`. Per-round artefacts under `lineage/` and `abandoned/`.")
    return "\n".join(lines)


def render_html(summary: dict[str, Any]) -> str:
    """Render a session summary as a self-contained HTML page."""
    title = html.escape(str(summary.get("source", "QALLM session")))
    strategy = html.escape(str(summary.get("strategy", "?")))
    judge = html.escape(str(summary.get("judge_strategy", "?")))
    model = html.escape(str(summary.get("model", "?")))
    accepted = summary.get("rounds_accepted_total", 0)
    abandoned = summary.get("rounds_abandoned_total", 0)
    halt = html.escape(summary.get("halt_reason") or "completed")

    cost = summary.get("cost", {})
    usd = cost.get("total_cost_usd", 0.0)
    tokens = cost.get("total_tokens", 0)
    elapsed = summary.get("budget", {}).get("elapsed_seconds", 0.0)

    parts: list[str] = []
    parts.append(_HTML_HEAD.format(title=title))
    parts.append(f"<h1>QALLM session report</h1>")
    parts.append(f"<p class='meta'><b>Source:</b> <code>{title}</code></p>")
    parts.append(
        f"<p class='meta'>"
        f"<b>Strategy:</b> {strategy} &middot; "
        f"<b>Judge:</b> {judge} &middot; "
        f"<b>Model:</b> {model}</p>"
    )

    parts.append("<h2>Totals</h2><ul>")
    parts.append(f"<li>Rounds accepted: <b>{accepted}</b></li>")
    parts.append(f"<li>Rounds abandoned: <b>{abandoned}</b></li>")
    parts.append(f"<li>Halt reason: <b>{halt}</b></li>")
    parts.append(f"<li>Cost: <b>${usd:.4f}</b> USD, {tokens} tokens</li>")
    parts.append(f"<li>Wall-clock: <b>{elapsed:.1f}s</b></li>")
    parts.append("</ul>")

    tracks = summary.get("tracks", {})
    if tracks:
        parts.append("<h2>Per-unit results</h2>")
        for unit_id, track in tracks.items():
            parts.append(f"<h3><code>{html.escape(unit_id)}</code></h3>")
            lineage = track.get("lineage", [])
            abandoned_list = track.get("abandoned", [])
            parts.append(
                f"<p>Lineage: <b>{len(lineage)}</b> accepted; "
                f"Abandoned: <b>{len(abandoned_list)}</b>.</p>"
            )

            if lineage:
                parts.append("<table><thead><tr>"
                            "<th>Round</th><th>Outcome</th><th>Explanation</th>"
                            "</tr></thead><tbody>")
                for entry in lineage:
                    rn = entry.get("round_number", "?")
                    jv = entry.get("judge_verdict")
                    if jv is None:
                        outcome_cls = "accepted"
                        outcome = "accepted (round 1)"
                        expl = "<em>unconditional</em>"
                    else:
                        outcome_raw = jv.get("outcome", "?")
                        outcome_cls = outcome_raw
                        outcome = outcome_raw
                        expl = html.escape(_truncate(jv.get("explanation", ""), 200))
                    parts.append(
                        f"<tr><td>{rn}</td>"
                        f"<td class='outcome {outcome_cls}'>{outcome}</td>"
                        f"<td>{expl}</td></tr>"
                    )
                parts.append("</tbody></table>")

            if abandoned_list:
                parts.append("<h4>Abandoned variants</h4>")
                parts.append("<table><thead><tr><th>Round</th><th>Reason</th></tr></thead><tbody>")
                for entry in abandoned_list:
                    rn = entry.get("round_number", "?")
                    jv = entry.get("judge_verdict") or {}
                    expl = html.escape(_truncate(jv.get("explanation", ""), 200))
                    parts.append(
                        f"<tr><td>{rn}</td>"
                        f"<td class='outcome regression'>{expl}</td></tr>"
                    )
                parts.append("</tbody></table>")

    sessions = summary.get("sessions", [])
    if sessions:
        parts.append("<h2>Verification sessions</h2>")
        parts.append("<table><thead><tr>"
                    "<th>Function</th><th>Rounds</th>"
                    "<th>Coverage</th><th>Bugs found</th>"
                    "</tr></thead><tbody>")
        for s in sessions:
            fn = html.escape(str(s.get("function") or s.get("function_name", "?")))
            r = len(s.get("rounds", [])) if isinstance(s.get("rounds"), list) else "?"
            cov = s.get("final_coverage")
            cov_s = f"{cov:.1f}%" if isinstance(cov, (int, float)) else "n/a"
            bugs = s.get("final_bugs", 0)
            parts.append(
                f"<tr><td><code>{fn}</code></td><td>{r}</td>"
                f"<td>{cov_s}</td><td>{bugs}</td></tr>"
            )
        parts.append("</tbody></table>")

    parts.append("<hr><p class='footer'>Generated from <code>summary.json</code>. "
                "Per-round artefacts under <code>lineage/</code> and <code>abandoned/</code>.</p>")
    parts.append(_HTML_FOOT)
    return "\n".join(parts)


# ----- helpers -----


def _truncate(text: str, max_chars: int) -> str:
    if not isinstance(text, str):
        return ""
    text = text.replace("\n", " ").strip()
    return text if len(text) <= max_chars else text[: max_chars - 1] + "..."


def _md_escape(text: str) -> str:
    """Escape pipe characters so a table cell doesn't break the row."""
    return text.replace("|", "\\|")


_HTML_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>QALLM report: {title}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          max-width: 980px; margin: 2em auto; padding: 0 1em; color: #222; }}
  h1, h2, h3, h4 {{ color: #1a3a5c; }}
  code {{ background: #f4f4f4; padding: 1px 4px; border-radius: 3px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left;
            font-size: 0.92em; vertical-align: top; }}
  th {{ background: #f0f4f8; }}
  .meta {{ color: #555; }}
  .outcome.improvement {{ color: #1a7f37; font-weight: bold; }}
  .outcome.regression {{ color: #b42318; font-weight: bold; }}
  .outcome.no_change {{ color: #6c757d; }}
  .outcome.accepted {{ color: #1a7f37; }}
  .footer {{ font-size: 0.85em; color: #777; }}
</style>
</head>
<body>
"""

_HTML_FOOT = """</body>
</html>
"""


def write_views(summary: dict[str, Any], session_dir: Path) -> tuple[Path, Path]:
    """Convenience: render and write report.md and report.html to ``session_dir``.

    Returns ``(md_path, html_path)``.
    """
    md = render_markdown(summary)
    h = render_html(summary)
    md_path = session_dir / "report.md"
    html_path = session_dir / "report.html"
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(h, encoding="utf-8")
    return md_path, html_path
