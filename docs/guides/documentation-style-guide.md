# QALLM documentation style guide

How we write QALLM docs, so that 28+ documents read as one voice and a reader
(an examiner, a supervisor, a future maintainer, or a new contributor) always
knows where to look and what to expect. This guide is itself written in the
style it describes.

## The six categories (where a doc goes)

Every doc lives in exactly one of these, and the choice is about the reader's
intent, not the topic:

- **concepts/**: the ideas. Why QALLM works the way it does. Read to understand.
  (verification gap, oracles and defect classes.)
- **architecture/**: how the system is built. Components, data flow, design
  decisions. Read to change the code safely.
- **guides/**: how to do a task. Deploy, run an experiment, use the Jupyter
  magic. Read to get something done now.
- **experiments/**: protocols and findings. What we ran, what we found. Read to
  trust or reproduce a result.
- **thesis/**: the research record. Roadmap, methodology decisions, session
  log, draft scaffold. Read to track the thesis itself.
- **showcase/**: demo-facing material. Read to present QALLM to others.

If a doc seems to fit two, ask what the reader wants when they open it
(understand vs change vs do vs trust vs track vs present) and place it there.
Link to the others rather than duplicating.

## Document shape

- Start with a one or two sentence statement of what the doc is and who it is
  for. No throat-clearing, no "in this document we will".
- Use sentence-case headings (`## The data model`, not `## The Data Model`).
- Prefer short sections with descriptive headings over long unbroken prose; a
  reader should be able to scan the headings and find their answer.
- State the conclusion first, then support it. An examiner reads the first
  paragraph of each section; make it carry the point.
- End findings and design docs with what to do next (a gate, a re-run, an open
  question), not a summary that repeats the body.

## Status markers

Architecture and design docs mix "how it is" with "how it will be". Mark each
clearly so a reader never implements a proposal as if it were current:

- `### Status: implemented` / `### Status: design` / `### Status: proposed`.
- When a doc describes a change in flight, say which parts are live and which
  are planned, in the opening sentence.

## Source-of-truth discipline

- A design decision is recorded once, in the right architecture or thesis doc,
  and other docs link to it. We do not restate decisions in three places where
  they will drift.
- `thesis/methodology-decisions.md` is the append-only log of methodology
  decisions (MD-NNN). `thesis/session-log.md` is the append-only record of what
  changed each working session. Neither is edited retroactively; new entries go
  on top (session log) or at the end (decisions), dated.
- When behaviour changes, update the doc that describes it in the same change
  that alters the code, and note it in the session log.

## Diagrams

- Use mermaid for flow, sequence, and structure. A diagram earns its place when
  it shows a relationship that prose makes the reader assemble in their head
  (a pipeline, a decision branch, a before/after).
- Every diagram has a sentence before it saying what to look for, and a
  sentence after it stating the takeaway. A diagram is not self-explanatory.
- Keep node labels short; put the explanation in the surrounding prose.

## Evidence and claims

- Quantitative claims cite their source: a run id, a metrics file, an artifact
  path. "reliability_gap caught 2 of 5 (session 20260610_011331)" not
  "detection improved".
- Distinguish what we observed from what we infer. Findings docs separate the
  evidence (the artifact showed X) from the interpretation (this means Y).
- Be honest about limitations in the doc that makes the claim, not in a
  separate caveats file. An examiner trusts a doc that states its own bounds.

## Voice and mechanics

- Plain, direct sentences. Active voice. Address the reader as needed without
  ceremony.
- Define an acronym on first use per doc (RQ, ENVRI, oracle), then use it.
- Code, file paths, identifiers, and CLI flags in backticks.
- Do not use hyphens, double hyphens, or triple hyphens as sentence
  punctuation; use commas, semicolons, colons, or parentheses. (This is a
  project-wide writing convention; apply it silently, do not annotate it in the
  text.)
- Prefer "round 0", "code unit", "verification gap", "oracle", "finding",
  "confirm/refute", "verified fix" as the standard vocabulary; do not introduce
  synonyms for established terms.

## Logging conventions

Logging is documentation for operators, so it follows the same discipline. The
levels mean specific things:

- **INFO**: milestones an operator watching a run wants to see, one per
  meaningful step, not one per iteration. "Verifying f [3/12] in round 2",
  "Gap experiment: 289 inputs, 0 done", "Consensus merge for f: 5/5 valid".
  A reader skimming INFO should see the run progress, not a firehose.
- **DEBUG**: the per-iteration and per-item detail useful when diagnosing a
  specific failure: each generated test's validation result, per-sample timing,
  intermediate token counts. Off by default; on when chasing a bug.
- **WARNING**: something recovered from but worth knowing: a sample was
  invalid, a test was dropped, a fixture was missing. Not for normal flow.
- **ERROR**: the operation failed and the run is affected.

Rules of thumb:
- If a line fires once per function-per-round (or more often), it is almost
  certainly DEBUG, not INFO. Per-round test-execution detail is DEBUG; the
  round's verdict is INFO.
- Method and event names in log messages start with a verb and read uniformly
  ("Generating ...", "Verifying ...", "Repairing ...", "Dropped ..."), so a
  grep on the verb finds the whole class of events.
- One idea per line; do not pack several facts into one message. Structured
  fields (key=value) are easier to grep than prose.
- Never log secrets (API keys, tokens) at any level.

When in doubt, ask: would an operator running ENVRI over hundreds of notebooks
want this line every time? If not, it is DEBUG.

## The docs index

`docs/README.md` lists every doc with a one-line description, grouped by
category. When you add a doc, add its line to the index in the same change. The
index is the map; a doc not on it is effectively lost.

## A short checklist before committing a doc

- It is in the right category for the reader's intent.
- It opens with what it is and who it is for.
- Current vs proposed is marked.
- Claims cite a source; evidence and interpretation are separated.
- Diagrams have a lead-in and a takeaway.
- It is linked from `docs/README.md`.
- The standard vocabulary and the punctuation convention are followed.
