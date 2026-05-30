# QALLM web UI: history views (Experiments and Sessions)

The QALLM web UI has three top-level views, selected from the switch in
the header:

- **Pipeline**: the step wizard that runs the pipeline on uploaded code.
- **Experiments**: browse historical HumanEvalFix validation runs.
- **Sessions**: browse every session the pipeline has ever processed.

The Experiments and Sessions views are read-only browsers over artefacts
already written to disk. Neither launches work; they reflect what the CLI
and the pipeline produced. This separation matters for a research tool:
the durable record is on disk, and the UI is a lens over it that survives
server restarts.

## Where the data lives

```
  producer                    on disk                         UI view
  ────────                    ───────                         ───────
  scripts/run_humaneval.py    $QALLM_RUNS_DIR/<run>/          Experiments
    (CLI, hours-long)           manifest.json                   tab
                                results.jsonl
                                aggregates.json
                                report.md

  orchestrator.run()          $QALLM_SESSIONS_DIR/<id>/       Sessions
    (Pipeline tab, or           summary.json                    tab
     CLI run_qallm.py)          report.md
                                round_00_baseline/
                                lineage/round_NN/...
                                abandoned/round_NN/...
```

Both directories are configurable by environment variable:

- `QALLM_RUNS_DIR` (default `runs`) for experiments.
- `QALLM_SESSIONS_DIR` (default `outputs/quality_reporter`) for sessions;
  this must match the `base_dir` the orchestrator gives its
  `QualityReporter`.

In the Docker stack, mount the host directory holding these into the api
container and set the variables so past runs and sessions appear.

## Request flow

```
  Browser (SessionsView / ExperimentsView)
     │
     │  GET /api/library                 GET /api/experiments
     │  GET /api/library/{id}            GET /api/experiments/{id}
     │  GET /api/library/{id}/report     GET /api/experiments/{id}/results
     │                                   GET /api/experiments/{id}/report
     ▼
  sessions_library router /              experiments router
  experiments router
     │  read-only:
     │    - index dirs (newest first)
     │    - parse summary.json / manifest.json / aggregates.json
     │    - stream report.md text
     │  guarded: id must be a single path segment (no traversal)
     ▼
  disk (QALLM_SESSIONS_DIR / QALLM_RUNS_DIR)
```

## Sessions view

- **List**: one card per session directory, newest first, showing the
  source file, the session id (the reporter's timestamp run-id), strategy,
  model, profile, and the accept/abandon round totals at a glance.
- **Detail**: a stats grid (strategy, model, profile, oracle, functions
  verified, rounds accepted/abandoned, halt reason), a cost line (total
  USD and tokens), and the full `report.md` inline.

## Experiments view

- **List**: one card per run directory, with strategies, models, round
  count, and result count.
- **Detail**: per-(strategy, model) aggregate cards (bug-detection and
  repair-success rates with counts, plus mean rounds/cost/time), a
  per-problem results table, and the markdown report inline.

## Why read-only

Experiment runs take hours and download datasets, and pipeline sessions
are launched either from the Pipeline tab or the CLI. Making these views
read-only keeps a clean separation: producing results is an explicit,
resource-aware action; reviewing them is cheap and safe. It also means the
history views never mutate the record an examiner or co-author is auditing.
