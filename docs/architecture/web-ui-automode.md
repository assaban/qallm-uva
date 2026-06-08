# QALLM web UI: auto mode

This guide explains the auto-mode flow in the QALLM web interface as of NEW-08. Auto mode lets you upload code, configure once, and watch the full v3 pipeline run without clicking through individual steps. It is the recommended demo mode and the easiest way to validate a fresh deployment end-to-end.

## When to use which mode

The Upload screen offers two execution modes:

**Manual** is the click-through flow. After upload you advance one step at a time: Analyse, Repair, Re-analyse, Test generation, Results. Each step waits for you. Useful for inspecting intermediate state, for screenshots of a specific stage, or for explaining the pipeline to someone unfamiliar with it.

**Automatic** is the one-shot flow. After upload, the orchestrator runs the full v3 loop: baseline static analysis, then N rounds of (repair → analyse → verify → judge), with per-unit accept/abandon decisions and budget caps enforced. You see the same Results screen at the end. Useful for benchmarking, for unattended runs (let it finish while you do other work), and for demo presentations where the manual flow's clicking would be distracting.

Both modes produce identical artefacts on disk (`summary.json`, `lineage/`, `abandoned/`, `report.md`, `report.html`). The difference is only in the user interaction surface.

## What auto mode actually does

When you click "Run Full Pipeline" in auto mode, the frontend kicks off a background job. That job, on the API side, calls `orch.run(source_path)`. The orchestrator:

1. **Round 0 (baseline).** Ingests source, runs static analysis only, persists to `round_00_baseline/`. No repair, no verification.

2. **Rounds 1..N.** Per unit, per round: analyse, repair, verify (generate tests, execute in sandbox, score with reward function), build a ProfileVerdict across all five EVERSE dimensions, judge variant vs parent, accept or abandon. Each unit's lineage evolves independently.

3. **Budget enforcement.** At each round boundary the orchestrator checks five caps (max rounds, max seconds, max round-seconds, max tokens, max cost USD). The first cap to trip halts the loop and records the reason.

4. **Reporter.** After every round, per unit, six artefacts land on disk: `source.py`, `static.json`, `verification.json`, `profile.json`, `judge.json`, `tests/`. Accepted variants go to `lineage/round_NN/<unit>/`; rejected variants go to `abandoned/round_NN/<unit>/`.

5. **Summary.** A `summary.json` aggregates per-unit tracks, judge verdicts, halt reason, and cost. `report.md` and `report.html` are derived views; both land in the session directory.

The Results screen surfaces the headline numbers: halt-reason badge, total accepted/abandoned counts, per-unit lineage tables with judge explanations, learning-curve chart, coverage chart, cost summary, deep link to the disk artefacts.

## Configuring an auto-mode run

All configuration is on the Upload screen, locked in at session start. Once a session begins, the orchestrator's parameters do not change. This matches how the orchestrator's `BudgetCaps` and `TestStabilityConfig` work internally and avoids ambiguity about which round used which settings.

**Basic settings** (always visible):

| Setting | What it does |
|---------|--------------|
| LLM model | The session's default model. Repair and test generation both use it unless overridden in Advanced. |
| Strategy | `rl` (default, iterative with reward feedback), `oneshot` (single generation, no feedback), or `hypothesis` (property-based, no LLM). |
| Oracle | `crash` (default), `property`, or `metamorphic`. Controls how generated tests probe the function. |
| Rounds | Maximum number of QALLM rounds (default 5). |

**Advanced settings** (collapsible panel, all optional):

| Setting | What it does |
|---------|--------------|
| Repair model | Override the LLM used for code repair. If unset, inherits the session default. |
| Test-gen model | Override the LLM used for test generation. If unset, inherits the session default. |
| Judge strategy | `lexicographic` (default), `strict`, or `model` (LLM-driven). Decides accept/abandon at each round. |
| Test stability | `frozen` (default, tests carry across rounds) or `per_round` (tests regenerated each round). |
| Generation policy | `grow` (default, tests accumulate) or `replay_only` (only latest round's tests run). |
| Budget caps | `max_tokens`, `max_seconds`, `max_round_seconds`, `max_cost_usd`. Leave blank for sensible defaults. |

The Advanced panel collapses by default so the basic flow stays uncluttered. Each Advanced row has a one-line explanation of what the option does so you don't have to remember the meaning.

## Reading the Results screen

The Results screen surfaces the v3 outcomes:

**Session outcome banner.** A halt-reason badge (green for completed normally, amber for budget-tripped) plus headline counters: rounds accepted, rounds abandoned, judge strategy, elapsed wall-clock, total cost in USD and tokens. Both `repair_model` and `testgen_model` labels appear separately so it is unambiguous which model did which work.

**Per-unit lineage panels.** One panel per code unit. Each panel shows the unit's lineage (accepted variants, with the judge's outcome and explanation per round) and any abandoned variants (with the rejection reason). Round 1 is always tagged "accepted (round 1)" with an italic "unconditional" note since there was no parent to compare against.

**Learning curve.** Cumulative reward per function across rounds. A rising line indicates the RL loop is learning; a flat or oscillating line suggests early convergence or instability.

**Coverage chart.** Final test coverage per function. Useful for spotting functions where the test generator failed to probe deeply.

**Bugs callout.** Per function and per round, any bugs discovered by the generated tests. This is the verification-gap evidence: bugs caught by execution that static analysis missed.

**Exports.** Downloads for the generated tests (concatenated text bundle) and the full result JSON. A deep link to the session's directory on disk so you can browse `summary.json`, `report.md`, `report.html`, and the per-round artefacts directly.

## Resumption and re-runs

The web UI itself does not support resumption: if you close the tab during a run, the job continues server-side but the UI loses its handle. The job's results stay in the session directory and can be inspected directly on disk.

The CLI variant (`python -m qallm.run_qallm ...`) supports the same flow plus checkpointing-via-disk: re-running with the same `--output` skips already-completed combinations. For the HumanEvalFix experiment specifically (`scripts/run_humaneval.py`), the runner streams results to `results.jsonl` and is fully crash-resumable.

For demo presentations, run a small example first (5 rounds, one short file, defaults) to make sure your local LLM provider is reachable. A pilot at this scale takes 1-3 minutes and uses negligible budget.

## Common issues

**"Job failed with AttributeError: 'str' object has no attribute 'value'."** Fixed in the post-NEW-08 hotfix; if you see this on a pre-hotfix build, pull dev and rebuild.

**"ModuleNotFoundError: No module named 'datasets'."** Only relevant to the HumanEvalFix experiment, not the web UI. Install the experiments extras: `pip install -e ".[experiments]"`.

**Repair model and test-gen model both fall back to default unexpectedly.** Check the Advanced panel: if a model selector shows "(use default)," that subsystem is inheriting. Select a specific model from the dropdown to override.

**Budget cap trips immediately.** The caps are total-session ceilings, not per-round. If `max_tokens=1000` and your first analyse call uses 800 tokens, you have 200 left for everything else. Set generous caps for unattended runs.
