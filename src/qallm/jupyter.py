"""QALLM Jupyter integration: an IPython magic to run the pipeline.

This is the FEAT-10 frontend trigger, built as an IPython magic because
that is where the research community actually works: inside notebooks, in
Jupyter, JupyterLab, and VS Code notebooks, all of which support IPython
magics with no extension to install. It wraps the same
:class:`QALLMOrchestrator` the CLI and web UI use, so results are
consistent across every entry point, and it adds no JavaScript packaging
to maintain.

Usage, once loaded::

    %load_ext qallm.jupyter

    # Run on the code in this cell:
    %%qallm --strategy feedback --rounds 3
    def divide(a, b):
        return a / b

    # Or run on a notebook / file / directory by path:
    %qallm path/to/analysis.ipynb --strategy oneshot

The cell magic (``%%qallm``) writes the cell body to a temporary .py file
and runs the pipeline on it. The line magic (``%qallm <path>``) runs the
pipeline on an existing path (.py, .ipynb, directory, .zip, or GitHub
URL), exactly like the ``qallm`` CLI.

Results render as an inline HTML summary in the notebook (with a plain
text fallback), and the full summary dict is returned so it can be
captured for further analysis::

    result = %qallm mymodule.py
"""

from __future__ import annotations

import html
import shlex
import tempfile
from pathlib import Path
from typing import Any

# The magic is only useful inside IPython. Importing IPython at module load
# would make qallm depend on it, so the registration function imports it
# lazily and raises a clear error if it is missing.


def _build_orchestrator(args) -> Any:
    """Construct an orchestrator from parsed magic arguments.

    Mirrors run_qallm.main so the magic behaves like the CLI. Kept in one
    place so the two entry points cannot drift apart.
    """
    from qallm.config import settings
    from qallm.cost import BudgetCaps
    from qallm.orchestrator import QALLMOrchestrator
    from qallm.profiles import LifecycleStage

    stage = LifecycleStage(args.stage)
    caps = BudgetCaps.from_kwargs(
        max_rounds=args.rounds,
        max_tokens=args.max_tokens if args.max_tokens is not None else settings.TOKEN_BUDGET,
        max_seconds=settings.QALLM_MAX_SECONDS,
        max_round_seconds=settings.QALLM_MAX_ROUND_SECONDS,
        max_cost_usd=args.max_cost_usd if args.max_cost_usd is not None else settings.QALLM_MAX_COST_USD,
    )
    return QALLMOrchestrator(
        stage=stage,
        strategy=args.strategy,
        llm_type=args.llm,
        model_name=args.model,
        oracle=args.oracle,
        rounds=args.rounds,
        caps=caps,
    )


def _make_arg_parser():
    """Argument parser for the magic, a subset of the CLI's options."""
    import argparse

    p = argparse.ArgumentParser(prog="%qallm", add_help=True)
    p.add_argument("source", nargs="?", default=None,
                   help="Path for the line magic; omitted for the cell magic.")
    p.add_argument("--strategy", default="feedback",
                   choices=["hypothesis", "oneshot", "feedback"])
    p.add_argument("--llm", default="openai", choices=["openai", "anthropic", "ollama"])
    p.add_argument("--model", default=None)
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--oracle", default="crash", choices=["crash", "property", "metamorphic"])
    p.add_argument("--stage", default="implementation",
                   choices=["draft", "implementation", "publication"])
    p.add_argument("--max-tokens", type=int, default=None, dest="max_tokens")
    p.add_argument("--max-cost-usd", type=float, default=None, dest="max_cost_usd")
    return p


def _summary_html(summary: dict) -> str:
    """Render a compact, readable HTML summary of a run for the notebook."""
    cost = summary.get("cost", {}) or {}
    rows = [
        ("Source", summary.get("source")),
        ("Strategy", summary.get("strategy")),
        ("Model", summary.get("model")),
        ("Units analyzed", summary.get("units_analyzed")),
        ("Functions verified", summary.get("functions_verified")),
        ("Rounds accepted", summary.get("rounds_accepted_total")),
        ("Rounds abandoned", summary.get("rounds_abandoned_total")),
        ("Halt reason", summary.get("halt_reason")),
        ("Total cost (USD)", f"{cost.get('total_cost_usd', 0):.4f}"),
    ]
    body = "".join(
        f"<tr><td style='padding:2px 12px 2px 0;color:#64748b'>{html.escape(str(k))}</td>"
        f"<td style='padding:2px 0;font-weight:600;color:#0f172a'>{html.escape(str(v))}</td></tr>"
        for k, v in rows
    )
    # Per-function coverage / bugs, if present.
    fn_rows = ""
    for s in summary.get("sessions", []) or []:
        name = html.escape(str(s.get("function_name", "?")))
        cov = s.get("final_coverage")
        bugs = s.get("final_bugs")
        cov_s = "n/a" if cov is None else f"{cov:.0f}%"
        fn_rows += (
            f"<tr><td style='padding:2px 12px 2px 0;font-family:monospace'>{name}</td>"
            f"<td style='padding:2px 12px 2px 0;color:#64748b'>{cov_s} cov</td>"
            f"<td style='padding:2px 0;color:{'#b91c1c' if bugs else '#15803d'}'>{bugs if bugs is not None else 0} bug(s)</td></tr>"
        )
    fn_block = (
        f"<div style='margin-top:8px'><div style='font-size:12px;color:#64748b;"
        f"text-transform:uppercase;letter-spacing:.05em'>Per function</div>"
        f"<table style='font-size:13px;margin-top:4px'>{fn_rows}</table></div>"
        if fn_rows else ""
    )
    return (
        "<div style='border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px;"
        "font-family:system-ui,-apple-system,sans-serif;max-width:560px'>"
        "<div style='font-weight:700;color:#4f46e5;margin-bottom:8px'>QALLM run complete</div>"
        f"<table style='font-size:13px'>{body}</table>{fn_block}"
        "<div style='margin-top:8px;font-size:11px;color:#94a3b8'>"
        "Bugs found by execution, not static analysis. Full artefacts saved to the session directory.</div>"
        "</div>"
    )


def _run_from_args(argv: list[str], cell: str | None) -> dict | None:
    parser = _make_arg_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        # argparse already printed help / the error to the cell output.
        return None

    if cell is not None:
        # Cell magic: write the cell body to a temp .py and run on it.
        tmp_dir = Path(tempfile.mkdtemp(prefix="qallm_cell_"))
        source_path = tmp_dir / "cell.py"
        source_path.write_text(cell, encoding="utf-8")
        target = str(source_path)
    else:
        if not args.source:
            print("Provide a path: %qallm <path> [options], or use the "
                  "%%qallm cell magic to run on the cell's code.")
            return None
        target = args.source

    orchestrator = _build_orchestrator(args)
    summary = orchestrator.run(target)

    # Render inline. Use IPython's display when available; fall back to text.
    try:
        from IPython.display import HTML, display
        display(HTML(_summary_html(summary)))
    except Exception:  # noqa: BLE001 - display is best-effort
        cost = summary.get("cost", {}) or {}
        print("QALLM run complete")
        print(f"  strategy: {summary.get('strategy')}  model: {summary.get('model')}")
        print(f"  verified: {summary.get('functions_verified')}  "
              f"accepted: {summary.get('rounds_accepted_total')}  "
              f"cost: ${cost.get('total_cost_usd', 0):.4f}")
    return summary


def load_ipython_extension(ipython) -> None:
    """Register the %qallm line magic and %%qallm cell magic.

    Called by IPython for ``%load_ext qallm.jupyter``.
    """
    from IPython.core.magic import register_line_cell_magic

    @register_line_cell_magic
    def qallm(line: str, cell: str | None = None):  # noqa: D401
        """Run the QALLM pipeline on a cell (%%qallm) or a path (%qallm)."""
        argv = shlex.split(line) if line else []
        return _run_from_args(argv, cell)

    # Keep a reference so static analysers do not flag it as unused.
    ipython.user_ns.setdefault("_qallm_magic", qallm)
