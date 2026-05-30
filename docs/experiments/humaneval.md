# HumanEvalFix experiment

This experiment validates QALLM's bug-detection and repair capability against an external, peer-reviewed benchmark: BigCode's HumanEvalFix (the Python subset of `bigcode/humanevalpack`). It is the headline methodology validation cited in the thesis.

## What it measures

Two outcomes per (problem, strategy, model) combination:

**Bug detected** (true / false): QALLM's generated tests fail when run against the buggy solution AND pass when run against the canonical solution. The second clause excludes degenerate test suites that fail everything; it ensures the tests actually discriminate between buggy and correct code.

**Repair successful** (true / false): the dataset's hidden test suite (the `test` field of each HumanEvalFix record) passes against QALLM's repaired source. The hidden tests are an external oracle; using QALLM's own tests would be circular.

## Prerequisites

The experiment depends on Hugging Face's `datasets` library, which is an *optional* QALLM dependency (it is heavy and not needed for the core pipeline). Install the experiment extras once:

```
pip install -e ".[experiments]"
```

After this, `import datasets` works inside your venv and the runner can load `bigcode/humanevalpack` from the Hub. The first run downloads and caches the dataset; subsequent runs are offline.

If you see `ModuleNotFoundError: No module named 'datasets'`, the extras were not installed.

## Running the experiment

```
python scripts/run_humaneval.py \
    --output runs/heval_2026-05-23 \
    --models openai:gpt-4o-mini,ollama:gemma3:4b \
    --strategies rl,oneshot,hypothesis \
    --rounds 5 \
    --seed 42
```

This runs all 164 problems against both models with all three strategies. Roughly 982 QALLM runs (the `hypothesis` strategy is identical across models so its second model run is a no-op for cost, but does re-run).

For a pilot, restrict the sample:

```
python scripts/run_humaneval.py \
    --output runs/heval_pilot \
    --models openai:gpt-4o-mini \
    --strategies rl \
    --sample-size 20 \
    --rounds 3 \
    --seed 42
```

A 20-problem pilot with RL on gpt-4o-mini typically costs $1-3 USD and runs in 30-60 minutes.

## Cost and time estimates

| Configuration                                 | Approximate cost    | Approximate time     |
|-----------------------------------------------|---------------------|----------------------|
| 20 problems, 1 model, 1 strategy, 3 rounds    | $1-3 USD            | 30-60 minutes        |
| 164 problems, 1 model, 1 strategy, 5 rounds   | $10-30 USD          | 4-8 hours            |
| 164 problems, 1 model, 3 strategies, 5 rounds | $20-60 USD          | 8-18 hours           |
| 164 problems, 2 models, 3 strategies, 5 rounds| $30-80 USD          | 16-36 hours          |

Cost is dominated by the OpenAI / Anthropic LLM calls. Ollama models (gemma3, llama) are local and free in dollar terms; they contribute only wall-clock time and electricity. Estimates are based on the pilot runs in earlier QALLM work; verify with a small sample before committing to a full run.

## Resumability

Results are appended to `<output>/results.jsonl` one JSON line per (problem, strategy, model) combination as each completes. Re-running the same command after a crash automatically skips combinations already recorded.

The skipping logic uses the `(task_id, strategy, model)` triple as the key. If a combination errored on the first run, the error result is recorded in the JSONL and treated as "done" on re-run; this prevents an infinite retry loop on a deterministically failing problem. To retry errored problems, delete those lines from `results.jsonl` manually before re-running.

## Output artefacts

After a run completes the output directory contains:

```
runs/heval_2026-05-23/
├── manifest.json       Run parameters: models, strategies, seed, dates, etc.
├── results.jsonl       One JSON line per (problem, strategy, model).
├── aggregates.json     Per-(strategy, model) summary numbers.
└── report.md           Markdown report with headline tables.
```

The markdown report is the artefact to cite. It includes:

- The full manifest so a reviewer can reproduce.
- A headline table with bug-detection rate, repair-success rate, mean rounds, mean cost, mean elapsed time per (strategy, model).
- Pairwise Wilcoxon signed-rank tests between strategies (when scipy is available and N >= 6 per pair).
- A per-problem detail table.
- An errored-runs section listing any problems that failed mid-run.

## Viewing results in the Web-UI

Completed runs are browsable in the QALLM Web-UI under the **Experiments**
tab (top of the page, next to **Pipeline**). No experiment is launched
from the browser: runs take hours and download datasets, so they run from
the CLI as above. The UI reads the artefacts each run wrote.

### Data flow

```
  CLI                          disk (QALLM_RUNS_DIR)              Web-UI
  ───                          ────────────────────              ──────
  run_humaneval.py
     │ runs QALLM per
     │ (problem, strategy,
     │  model) combination
     ▼
  humaneval_runner          runs/<run-id>/
     │  writes  ───────────►   manifest.json     ┐
     │                         results.jsonl     │  GET /api/experiments
     │                         aggregates.json   ├─────────────────────►  ExperimentsView
     │                         report.md         ┘  GET /api/experiments/{id}
     │                                              GET .../{id}/results     run list
     ▼                                              GET .../{id}/report       │
  (resumable: appends                                                        ▼
   one JSONL line per                                              per-run detail:
   completed combination)                                          - aggregate cards
                                                                    (bug-detection +
                                                                     repair-success
                                                                     per strategy/model)
                                                                   - per-problem table
                                                                   - markdown report
```

The `experiments` API router (`src/qallm/api/routers/experiments.py`)
reads the run directory; it never writes. Point it at a different
location with the `QALLM_RUNS_DIR` environment variable (default `runs`).
In the Docker stack, mount your runs directory into the api container and
set `QALLM_RUNS_DIR` to the mount path so past runs appear in the UI.

### What the UI shows

- **Run list**: every run directory, newest first, with its strategies,
  models, round count, and result count.
- **Aggregate cards**: one per (strategy, model), with bug-detection rate
  and repair-success rate (and the underlying counts), plus mean rounds,
  cost, and time per problem. Comparing the cards is the headline result:
  the feedback (RL) strategy is expected to detect more bugs than one-shot
  or property-based generation.
- **Per-problem table**: each task with bug-detected / repaired flags,
  rounds, coverage, and cost. Errored problems are highlighted.
- **Markdown report**: the full `report.md`, including the Wilcoxon
  pairwise tests, viewable inline.

The experiment is deterministic *up to* LLM non-determinism. The seed controls only the sampling step (when `--sample-size` is set); the underlying QALLM pipeline uses the LLM at its configured temperature, which on OpenAI providers introduces server-side randomness even at `temperature=0`.

To compare two runs fairly, use the same seed, the same model, the same strategy, the same rounds, and accept that the absolute numbers will differ by a few percent across re-runs. The Wilcoxon test in the report makes pairwise *comparisons* robust to this noise even if absolute numbers shift.

## Interpreting the result

The thesis claim is two-pronged:

1. **The verification gap is real.** Static analysis tools (Bandit, Radon, Ruff) report no findings on most HumanEvalFix buggy programs because the bugs are semantic (wrong operator, wrong constant, off-by-one) rather than syntactic. QALLM's execution-based tests detect them. We expect a high bug-detection rate for the RL strategy, low for static-only, and intermediate for oneshot.

2. **The RL loop improves on one-shot.** RL with multiple rounds of feedback should outperform one-shot generation on bug-detection rate. The Wilcoxon p-values quantify the significance.

Hypothesis (property-based testing) is the no-LLM control. It will likely score low on bug detection because HumanEvalFix bugs are often semantic and not exposed by random input generation alone. That is the expected result; it underscores that LLM-guided test generation is doing real work over and above random fuzzing.

If RL ties or loses to oneshot in the experiment, that is a finding worth reporting in the thesis: it would mean the iterative feedback signal is too noisy at the configured number of rounds, and would motivate either more rounds, a different reward function, or a different model.

## Reading the JSON

For programmatic analysis, parse `results.jsonl`:

```python
import json
results = [
    json.loads(l) for l in
    open("runs/heval_2026-05-23/results.jsonl").read().splitlines() if l.strip()
]
# Filter to one strategy/model:
rl_gpt = [r for r in results if r["strategy"] == "rl" and "gpt-4o-mini" in r["model"]]
detection_rate = sum(r["bug_detected"] for r in rl_gpt) / len(rl_gpt)
```

For aggregates, parse `aggregates.json`, which is a list of per-(strategy, model) dicts with `bug_detection_rate` and `repair_success_rate` pre-computed.

## Known limitations

* The bug-detection check runs pytest in a subprocess with a 10-second timeout per test. Tests that legitimately need more than 10 seconds will be marked as "did not detect." In practice HumanEvalFix tests are tiny and complete in milliseconds; this is a safety net, not a real constraint.
* The runner extracts QALLM's "first valid test" from the latest round as the bug-detection probe. If a session has no valid tests across any round, the bug is recorded as not detected, regardless of repair outcome. This is faithful to "QALLM had nothing to say"; it does not artificially inflate the detection rate.
* HumanEvalFix is itself a curated benchmark; its 164 problems are not a random sample of real Python bugs. Generalisation to other bug distributions (e.g. Li's notebook corpus) is the next experiment, not this one.
