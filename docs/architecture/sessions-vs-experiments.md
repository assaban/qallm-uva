# Sessions versus experiments: storage and listing

This note documents how interactive web-UI sessions are kept separate from batch
experiment runs, so the Sessions tab stays fast and uncluttered. It exists
because the two produce very different volumes of artefacts and must not share a
listing.

## The two kinds of run

QALLM runs come from two places:

Interactive sessions come from the web UI (upload, analyse, run pipeline). There
are few of them, a user clicks through one at a time, and each is meant to be
browsed in detail in the Sessions tab.

Experiment runs come from the batch runner (`scripts/run_gap_experiment.py`).
One run can process thousands of notebooks, each producing its own per-unit
artefact directory. A single headline run (for example E1 over 1843 notebooks)
creates on the order of a thousand session-shaped directories.

If both were listed together, the thousands of experiment directories would
swamp the Sessions tab and slow it to a crawl. That is the problem this
separation solves.

## How they are separated

Every session writes a `summary.json` that now carries an `origin` field:

`origin: "interactive"` is set by the web layer when it constructs the
orchestrator (in `api/routers/sessions.py`). `origin: "experiment"` is the
default, used by the batch runner and anything that builds an orchestrator
without overriding it. The field is threaded orchestrator to reporter to
`summary.json` (`QualityReporter(origin=...)`).

The Sessions library endpoint (`GET /api/library`, in
`api/routers/sessions_library.py`) lists a directory only when its
`summary.json` is not marked `origin: "experiment"`. Sessions created before the
marker existed have no `origin` key and are treated as interactive, so existing
web sessions are never hidden; only runs explicitly marked as experiments are
excluded.

Experiment runs remain fully accessible through their own surface: the batch
runner writes them under the `--output` directory the user chooses (by
convention `runs/<name>`), and the dedicated experiments API
(`/api/experiments`, `api/routers/experiments.py`) lists and serves them. They
are not lost, they are simply not mixed into the interactive Sessions tab.

## Directory conventions

Interactive sessions: `outputs/quality_reporter/<run_id>` (the orchestrator's
default reporter base; overridable via `QALLM_SESSIONS_DIR`).

Experiment runs: wherever `--output` points, by convention `runs/<name>`, with
`results.jsonl`, `manifest.json`, `aggregate.json`, and (under full retention)
per-unit artefacts.

## Why a marker rather than just separate directories

Directory separation alone is fragile: it depends on every caller choosing the
right base directory, and a single misconfigured run can drop experiment
artefacts into the interactive directory and swamp the tab again. The `origin`
marker travels with the data, so the listing filter is correct regardless of
where the directories physically live. The directory convention and the marker
together are belt and braces.
