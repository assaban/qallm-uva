# Understanding a QALLM pipeline run: rounds, test accumulation, and statuses

This explains what happens inside a QALLM run, written against a real
session (the `domain.py` sample) so the log lines map to concepts. It also
records three issues that reading that log surfaced, two of which were real
bugs now fixed. The mechanics here are thesis material: they are exactly
the kind of methodological detail a reader needs to trust the numbers.

## The two round counters (and why a log said "Round 2" in round 1)

There are two different "round" notions, and they are 1 apart by design:

* **Pipeline round** (the orchestrator's): round 0 is the *baseline*
  (analyse and verify the *original* code, no repair), and rounds 1..N are
  *repair* rounds (repair, then verify the repaired variant, then judge
  accept/abandon against the parent).
* **Test-generation round** (the generator's): a 1-based count of how many
  times tests have been generated for a function. The baseline is
  generation 1, the first repair round is generation 2, and so on.

So during pipeline round 1, the generator was on its 2nd generation and
logged "Round 2". Harmless, but confusing. The generator now logs the
pipeline round instead, so the two line up. (The prompt content was always
correct; only the log label was off.)

## What "FROZEN+GROW: running N accumulated test(s)" means

This is the test-stability policy, and it is central to how QALLM judges
improvement fairly. Two independent settings combine:

* **Stability = FROZEN.** Once a test is generated and validated, it is
  kept and re-run unchanged in later rounds. The alternative, PER_ROUND,
  would regenerate tests each round. FROZEN matters because it keeps the
  yardstick stable: if the tests changed every round, you could not tell
  whether the code got better or the tests got easier.
* **Policy = GROW.** Each round the generator produces *new* feedback-driven
  tests (informed by the previous round's failures), and those are *added*
  to the kept set rather than replacing it. The alternative, REPLAY_ONLY,
  would only re-run the existing tests without adding new ones.

So FROZEN+GROW means: keep every validated test from every prior round, add
this round's new tests, and run the whole accumulated suite against the
current code variant. "Running 6 accumulated test(s)" means six rounds of
generation have each contributed tests and all of them now run together.

Why this design: it makes the test suite a monotonically growing,
stable oracle. A repair is judged against *all* tests found so far, so a
fix that silences this round's failing test but breaks something an earlier
round covered is caught. That is the no-regression principle, enforced by
accumulation.

The trade-off, visible in the log, is cost: the suite grows each round, so
later rounds run more tests and generation prompts get longer (more prior
context). For the `domain.py` run, `complex_branching` went from running a
handful of tests in round 0 to many by round 5. This is the right
trade-off for judging fairly, but it is worth surfacing the suite size and
cost per round in the UI so the growth is legible.

## "ERROR" vs "BUG" vs "PASS" on a test

Three distinct outcomes, and the distinction matters:

* **PASS**: the test ran and its assertions held. On the original (buggy)
  code, a passing test is one the code already satisfies.
* **BUG** (pytest "failed"): the test ran to completion and an assertion
  failed. This is the valuable signal: a concrete, reproducible defect the
  generated test caught by *executing* the code. The `complex_branching`
  failures are real examples: `complex_branching(30)` returned 50 where the
  test expected 43, with the exact diff shown.
* **ERROR** (pytest "error"): the test did **not** run to completion. It
  raised during collection, fixture setup, or teardown, before or around
  the assertion. An error is not evidence about the code under test; it is
  usually a problem with the *test itself*.

In the `domain.py` run, every `dangerous` test showed ERROR. The cause was
in the generated tests: they referenced a `fixed_obj` fixture that the
generated file never defined. pytest could not set up the fixture, so each
test errored during setup and never executed. That is why `dangerous`
showed 0 passes, 0 bugs, and a flat 31% coverage every round: its tests
never actually ran. The repaired code was being verified each round (the
repair did happen), but the broken tests could not exercise it.

Two bugs made this invisible and were fixed:

1. **The error message was empty.** The executor read a test's traceback
   only from pytest's "call" phase, but a setup error lands under "setup".
   So errored tests displayed "ERROR" with no explanation. Now the setup
   and teardown phases are read too, so the "fixture 'fixed_obj' not found"
   message is surfaced.
2. **Errored tests were counted as zero errors.** A singular/plural key
   mismatch (`error` vs `errors`) meant the error tally never incremented,
   so the count of errored tests was wrong. Fixed.

The deeper issue this exposes is about **generation quality**: the local
model (gemma4:e4b) produced tests referencing an undefined fixture. That is
a generator-robustness problem, not a pipeline-logic problem, and it points
at a worthwhile improvement: validate generated tests for undefined
fixtures/names before running them (an AST check), and either repair or
discard tests that reference symbols they never define. This would raise
the signal of the verification step, especially on smaller local models.

## Why round 1 looked like it used unrepaired code

It did not; the repair ran (the log shows "Repair completed: CLEAN" before
verification each round). The impression came entirely from the `dangerous`
function: because its tests all errored, its numbers (0 bugs, 31% coverage)
were identical every round, which reads as "nothing changed." With the
error messages now visible, this is no longer mistakable: an errored test
clearly shows a test-setup failure rather than a verification result.

## What this gives the thesis

These mechanics are reportable methodology:

* The FROZEN+GROW accumulation is the mechanism behind the no-regression
  guarantee, and explaining it justifies why QALLM's accept/abandon
  decisions are trustworthy rather than noise.
* The ERROR vs BUG distinction matters for the verification-gap claim: only
  BUGs are evidence of the gap; ERRORs are test-quality noise that must be
  filtered out before computing the false-confidence rate, or they would
  contaminate it.
* The generated-test fixture problem is itself a finding: it quantifies how
  much generation robustness affects measured bug-detection, and motivates
  the AST-validation improvement. Reporting that honestly strengthens the
  work.

## Follow-ups worth considering

1. Validate generated tests for undefined names/fixtures before running
   (AST check); repair or discard the rest. Highest-value, directly raises
   verification signal.
2. Surface per-round suite size and cost in the UI, so FROZEN+GROW's growth
   is legible.
3. Separate ERROR from BUG everywhere in the UI and metrics (errors are not
   bugs and must not count toward bug-detection or the false-confidence
   rate).
