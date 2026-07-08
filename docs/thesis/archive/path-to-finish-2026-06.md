> **Superseded.** Historical snapshot; the live status is `../STATUS.md`, the plan is `../roadmap.md`.

# Path to finish: audit and calibration, June 16

A clear-eyed status as E1 runs, what is solid, what the partial data revealed,
and the remaining path to a delivered thesis. Written so the finish line is
concrete.

## Where we are

The pipeline is complete, the instrument is calibrated, the engineering is clean
(724 tests, ruff clean), and the headline experiment (E1, the ENVRI verification
gap) is running. The partial data (the first ~955 of 1843 notebooks) already
shows the headline result materialising and surfaced two real bugs, both now
fixed.

## What the partial E1 data shows

- **RQ1 is real.** Across 893 successfully processed notebooks, execution found
  343 defects in functions that passed static analysis, in 118 distinct
  notebooks. The verification gap is not a lab artefact; it appears at scale on
  real research code. The final rate and its CI come from the completed run.
- **RQ2/RQ3 are zero, as expected.** This E1 run did not use `--confirm` (it is
  the RQ1 headline pass per the experiment plan). RQ2/RQ3 come from a separate
  `--confirm` pass; their zero here is correct, not a defect.
- **62 of 955 notebooks errored** with the same cause and were isolated (the run
  continued). At ~6.5% this is worth pinpointing; traceback logging is now in
  place so the next run identifies the exact line.

## Two bugs the data exposed, both fixed

1. **Confirm metrics were lost in aggregation.** The per-session rows carried
   `inconclusive` / `not_execution_testable`, but the re-aggregation and resume
   path silently dropped them, which is why `--confirm` lab runs kept showing
   zeros despite correct per-session verdict logs. Fixed the round-trip.
2. **Mutation confidence was almost all "unknown" on real code** (336 of 343).
   Data functions made the generated suite error on mutants, and an all-error
   run was discarded as not-viable. Fixed: when the suite runs cleanly on the
   original, a mutant that turns it to errors is detected (killed), not
   discarded. This should move much of the distribution out of "unknown" and is
   what makes the confidence contribution land on the headline corpus.

## Calibration status

The lab instrument remains sound (reliability 5/5, clean controls clean). The
two fixes above do not change the lab verdicts (the lab suites do not error on
mutants), they fix legibility (RQ2 numbers surviving aggregation) and real-data
behaviour (confidence on data functions). A single clean `--confirm`
`--mutation-confidence` lab run after merging will confirm both on ground truth:
expect `total_inconclusive` non-zero and a confidence distribution that is no
longer dominated by "unknown".

## The remaining path to deliver

In order, with dependencies:

1. **Merge the two fixes** and run one clean lab pass with `--confirm
   --mutation-confidence` to confirm RQ2 numbers survive and confidence
   populates. (Gate: instrument still sound after the fixes.)
2. **Let E1 finish**, then re-run the confidence scoring (it reads the persisted
   artefacts) so the headline carries a real confidence distribution, not the
   pre-fix "unknown" one. If E1 was already far along on the old code, a fresh
   confidence pass over its artefacts is enough; the gap counts themselves are
   unaffected by the confidence fix.
3. **Run E2/E3** (the `--confirm` pass on ENVRI) for RQ2/RQ3.
4. **Draft the results sections** (thesis 5.2 to 5.4) with the real numbers,
   plus the enrichment cuts that are now cheap: A1 confidence-stratified gap
   rate (uses the fixed confidence) and A2 per-EVERSE-dimension breakdown.
5. **Draft Discussion, Conclusion, Abstract** (5.6 scale if the Li corpus is in
   by then), making the thesis content-complete.
6. **Optional, time-permitting**: the A3 crash-vs-correctness ablation; surface
   gap-confidence inline in the `%%qallm` magic and on a live web-UI metrics
   page (Tier 3 demo).

## What is explicitly NOT on the critical path

Training an LLM (future work / PhD), safe security confirmation (future work),
and the broader oracle types. These are named in the thesis as future work and
must not pull focus from steps 1 to 5.

## One-line status

Instrument sound, headline materialising, two real bugs fixed; the path to
delivery is finish E1, fix-confirmed lab pass, RQ2/RQ3 run, then write the
results and closing chapters.
