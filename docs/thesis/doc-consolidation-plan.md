# Documentation consolidation and cleanup proposal

The repository carries 58 documentation files. Several overlap, a few are
superseded, and the naming does not always say why a file exists. This proposes
a consolidation so the docs are navigable and authoritative, with a clear rule
for what each file is for. Nothing here is deleted yet; this is for sign-off.
Git history preserves anything removed.

## Target structure and the rule for each folder

The guiding rule, stated once at the top of `docs/README.md`:
code > methodology log > everything else. If two docs disagree, the code wins,
then the methodology log, then the rest.

- `docs/guides/` end-user and operator how-tos (getting started, running
  experiments, deployment, SonarQube, jupyter magic). Keep.
- `docs/concepts/` the ideas (oracles, defect classes, mutation confidence,
  surpassing static analysers). Keep, with one merge below.
- `docs/architecture/` how the system is built (workflow, run mechanics,
  verification/repair/reward, sessions-vs-experiments, web UI). Keep.
- `docs/architecture/design/` the per-feature design records (FEAT-01..05).
  Keep as a historical design record; they are point-in-time and that is fine.
- `docs/experiments/` experiment protocol and results writeups. Keep, with the
  consensus doc retired (see below).
- `docs/thesis/` thesis-facing material. This is where the sprawl is; see the
  status-doc collapse below.
- `docs/project/` and `docs/showcase/` diagrams and showcase pages. Keep.

## The status-document collapse (the main fix)

`docs/thesis/` has four overlapping, dated status snapshots that say much the
same thing and drift apart:

- `status-update-2026-06.md` (12 KB)
- `status-checkpoint-2026-06-16.md` (4 KB)
- `path-to-finish-2026-06.md` (4 KB)
- `roadmap.md` (8 KB, forward-looking)

Proposal: keep exactly two living status artifacts and archive the rest.

- Keep `roadmap.md` as the single forward-looking plan.
- Create `STATUS.md` as the single point-in-time status, OVERWRITTEN in place
  rather than re-created per date. Fold the current content of
  `status-checkpoint-2026-06-16.md` into it.
- Move `status-update-2026-06.md`, `status-checkpoint-2026-06-16.md`, and
  `path-to-finish-2026-06.md` to `docs/thesis/archive/` (or delete; history
  keeps them). They stop competing for authority.

## Retire the consensus material (matches the audit and the methodology log)

Consensus-by-union is abandoned (methodology log; single-sample is the live
setting). Two docs still describe or recommend it:

- `docs/experiments/oracle-variance-and-consensus.md`
- `docs/experiments/lab-calibration-result.md` (recommends `--samples 5`)

Proposal: fold the one durable insight (why union failed: independent samples
pick different inputs, so call-keyed voting never triggers) into the
threats-to-validity narrative, then delete both, or prepend a "superseded by
single-sample, see methodology log" banner if kept for history. This pairs with
removing the consensus CODE (separate task) so docs and code agree.

## Merges (small, reduce overlap)

- `docs/concepts/oracles.md` and `docs/concepts/oracles-and-defect-classes.md`
  overlap. Merge into one `oracles.md` covering the four oracle types and the
  defect classes each targets.
- `docs/experiments/run-outline.md` and `docs/experiments/protocol.md` overlap
  with `docs/thesis/experiment-plan.md`. Keep `experiment-plan.md` as
  authoritative for the thesis runs; reduce the other two to operator notes or
  fold them in.

## Naming convention (so a file's purpose is obvious)

Adopt a light convention and state it in `docs/README.md`:

- guides: imperative how-to titles (`running-experiments`, `deployment`).
- concepts: the idea named directly (`oracles`, `verification-gap`).
- architecture: the subsystem named (`workflow-design`, `run-mechanics`).
- thesis: durable nouns (`experiment-plan`, `methodology-decisions`,
  `roadmap`, `STATUS`), no dates in living-doc names. Dated files belong in
  `archive/` only.
- one append-only log: `methodology-decisions.md`. The `session-log.md` is an
  engineering diary; keep it but mark it clearly as non-authoritative working
  notes.

## Proposed deletions for sign-off

These look genuinely obsolete; confirm before removal (history preserved):

1. The two consensus docs (after folding the insight into threats-to-validity).
2. Two of the three status snapshots (after the STATUS.md collapse).
3. Whichever of `run-outline.md` / `protocol.md` is fully subsumed by
   `experiment-plan.md` after the merge.

Everything else stays. The thesis-defensibility docs (audit, methodology log,
rq-evolution, security-confirmation-scope, llm-training-analysis) are kept; they
are exactly the artifacts a committee values, and they are not duplicative.

## Sequencing

Low risk, do first: the STATUS.md collapse and the naming/precedence line in
`docs/README.md`. Then the consensus retirement (docs together with the code).
Then the two merges. Each is a small, reviewable change.
