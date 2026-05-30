# Backlog: pipeline quality loop (issues to create)

These are the issues to open on `assaban/qallm-uva` for the quality-loop
work described in `docs/quality-loop-design.md`. They are written here in
the same way `backlog-audit-2026-05.md` records issues to create, because
they cannot be opened directly from the build environment. Create them on
GitHub when the backlog freeze lifts.

The work is deliberately staged so the shared harness lands first and the
two modes build on it. Suggested labels follow the existing scheme
(`RQ1` for anything touching the strategy/quality claim, plus a new
`quality-loop` label to group them).

---

## QLOOP-01: Quality harness (shared core)

**Labels:** quality-loop, RQ1
**Depends on:** the experiments runner (shipped).

A thin wrapper over the existing experiment runner that turns a run into a
labelled quality point: records the QALLM version (git SHA), the
configuration, the date, and the metric vector (bug-detection rate,
repair-success rate, false-confidence rate, mean rounds, cost), per
(strategy, model). Stores points in a run history that later issues read.

**Acceptance criteria**

* A function/CLI that runs the benchmark and writes one labelled point
  (SHA, config, date, metrics) to a history store.
* The metric vector includes false-confidence rate explicitly.
* History is append-only and readable by the regression and research
  tooling.
* Unit-tested with a stubbed runner (no network, no LLM).

---

## QLOOP-02: Regression mode

**Labels:** quality-loop, RQ1
**Depends on:** QLOOP-01.

Compare a candidate (branch/PR) against the stored baseline on the fixed
(non-held-out) benchmark slice, using the pairwise Wilcoxon test already in
the report so a few percent of LLM noise does not trip a false alarm.

**Acceptance criteria**

* Baseline storage: the metric vector of the current `dev` tip as the
  reference.
* Candidate-vs-baseline comparison per metric, with significance via the
  pairwise test.
* A report with per-metric delta, significance, and a verdict
  (pass / regression / inconclusive).
* Runnable on a branch (documented invocation).
* Tested with synthetic per-problem outcomes (no network).

---

## QLOOP-03: Research mode (prompt/strategy search)

**Labels:** quality-loop, RQ1
**Depends on:** QLOOP-01.

A variant registry where each variant changes exactly one knob (repair
prompt, test-generation prompt, judge strategy, or generation policy).
Run a variant against the current default on the tuning slice, compare with
the pairwise test, then confirm a winner once on the held-out slice before
promotion.

**Acceptance criteria**

* A variant registry: one knob per variant, named.
* Tuning-slice comparison (variant vs default) with the pairwise test.
* Held-out confirmation step; a variant that wins on tuning but not on
  held-out is rejected.
* A promotion step that makes a confirmed winner the new default and the
  new regression baseline.
* Tested with stubbed variants and synthetic outcomes.

---

## QLOOP-04: Held-out and notebook benchmarks

**Labels:** quality-loop, RQ1, RQ2
**Depends on:** QLOOP-01.

Reserve a held-out slice of HumanEvalFix that is never used for tuning
(needed by QLOOP-03's confirmation step), and add a notebook-derived
benchmark (Li's corpus) for the research-software distribution the thesis
targets, so the harness measures the distribution that matters, not only
curated single-function bugs.

**Acceptance criteria**

* A documented, fixed held-out split of HumanEvalFix.
* A loader for the notebook-derived benchmark in the same problem shape the
  harness consumes.
* Both selectable by the harness.

---

## Notes for whoever opens these

* QLOOP-01 is the only hard prerequisite; QLOOP-02 and QLOOP-03 can proceed
  in parallel once it lands.
* Keep one knob per variant in QLOOP-03; multi-knob changes make an effect
  unattributable and are out of scope for the first version.
* The pairwise test (Wilcoxon signed-rank over per-problem outcomes) is the
  same one in the experiment report; reuse it rather than reimplementing.
