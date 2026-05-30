# Pipeline quality loop: design

This document sketches a continuous, iterative process for improving
QALLM's own quality over time. It is a design, not an implementation: the
backlog freeze means we are not adding unrelated features right now, so
this records the plan and the issues to open, ready to build when the
freeze lifts.

The loop pulls in two complementary directions, both requested:

1. **Catching regressions (engineering discipline).** Every change to
   QALLM should be measured against a fixed yardstick so a change that
   quietly makes the pipeline worse is caught before it ships.
2. **Searching for improvements (research).** The pipeline should have a
   repeatable way to try prompt and strategy variants and tell, with
   evidence, whether a variant is actually better.

These share most of their machinery (a fixed benchmark, the same metrics,
the same runner), so they are two modes of one harness rather than two
systems.

## The shared core: a quality harness

A single harness runs QALLM against a fixed, labelled benchmark and emits
a small set of headline metrics. Both modes use it.

* **Benchmark.** Start with HumanEvalFix (already integrated: buggy
  programs, canonical fixes, hidden tests). Reserve a held-out slice that
  is never used for tuning, so research-mode search cannot overfit to the
  set it optimises against. Later, add a notebook-derived set (Li's corpus)
  for the research-software distribution the thesis targets.
* **Metrics.** The numbers the experiment already computes, treated as the
  quality vector of a QALLM version: bug-detection rate, repair-success
  rate, false-confidence rate (the verification-gap headline), mean rounds,
  and cost. These are computed per (strategy, model) so a change's effect
  is visible where it lands.
* **A run is a labelled point.** Each harness run records the QALLM
  version (git SHA), the configuration, the date, and the metric vector.
  Runs accumulate into a history that both modes read.

## Mode 1: regression catching

Goal: a change to QALLM is measured against the last known-good baseline
on the fixed (non-held-out) benchmark, and a drop beyond a tolerance is
flagged.

* **Baseline.** The metric vector of the current `dev` tip, stored as the
  reference. A new candidate (a branch, a PR) is run against the same
  benchmark slice with the same seed, model, and rounds.
* **Comparison.** Per metric, compare candidate to baseline. Because LLM
  calls are noisy, use the same pairwise approach the experiment report
  already uses (Wilcoxon signed-rank over per-problem outcomes) rather than
  comparing single aggregate numbers, so a few percent of noise does not
  trip a false alarm. A regression is a statistically significant drop in a
  primary metric (bug-detection or repair-success) or a significant rise in
  cost without a matching quality gain.
* **Surfacing.** A short report: per-metric delta, significance, and a
  verdict (pass / regression / inconclusive). Designed to be run on a
  branch before merge, the engineering yardstick.
* **Determinism caveat.** The harness pins seed, model, and rounds, and
  reports that absolute numbers still move a few percent across re-runs
  because of provider-side non-determinism. The pairwise test is what makes
  the verdict robust to that, not an attempt to remove the noise.

## Mode 2: prompt and strategy search

Goal: systematically try variants of the parts of QALLM we can change
(repair prompts, test-generation prompts, judge strategy, generation
policy) and tell whether a variant beats the current default.

* **What varies.** A variant is a named change to one knob: a repair-prompt
  template, a test-generation-prompt template, a judge strategy, or a
  generation policy. Exactly one knob at a time, so an effect is
  attributable.
* **How it is judged.** Run the variant and the current default on the same
  benchmark slice, same seed/model/rounds, and compare with the same
  pairwise test as Mode 1. A variant is an improvement if it significantly
  raises a primary metric without a disproportionate cost increase.
* **Guarding against overfitting.** Variants are searched on the tuning
  slice; the winner is then confirmed once on the held-out slice before it
  becomes the new default. A variant that wins on tuning but not on
  held-out is rejected. This is the discipline that keeps research-mode
  honest.
* **Promotion.** A confirmed winner becomes the new default and, in turn,
  the new regression baseline for Mode 1. The two modes feed each other:
  research raises the bar, regression-catching holds it.

## How the two modes relate

```
   research mode                          regression mode
   ─────────────                          ───────────────
   try variant on tuning slice            run candidate vs baseline
        │                                      │
        ▼                                      ▼
   pairwise test vs default               pairwise test vs baseline
        │ wins?                                │ regressed?
        ▼                                      ▼
   confirm on held-out slice              flag before merge
        │ confirmed?                           │
        ▼                                      │
   promote to default ───────────────────────►│  (new baseline)
```

## Build order (when the freeze lifts)

1. Extract the harness: a thin wrapper over the existing experiment runner
   that records the version SHA and the metric vector as a labelled point,
   and stores the run history.
2. Regression mode: baseline storage, candidate-vs-baseline comparison with
   the pairwise test, and a pass/regression/inconclusive report. Wire it so
   it can run on a branch.
3. Research mode: a variant registry (one knob per variant), the
   tuning-then-held-out confirmation flow, and a promotion step.
4. A held-out benchmark slice, and later a notebook-derived benchmark for
   the research-software distribution.

## Why this serves the thesis

The false-confidence rate is the thesis's empirical claim. A harness that
tracks it over QALLM versions turns that claim into a living measurement:
the thesis can report not just one number but the trajectory as the
pipeline improved, and can show that prompt/strategy changes moved it in a
measurable, statistically defensible way. Regression-catching keeps the
reported numbers trustworthy; research-mode search is how the numbers get
better.
