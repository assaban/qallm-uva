# What the round-by-round artefacts show, and the fix

Session 20260618_071812 (reliability_gap, correctness oracle, web UI). I went
through the per-round test files in lineage and abandoned. Two things stand out:
one is good and we should lean on it, one is a real bug you correctly spotted.

## Good: tests accumulate and re-run, and the judge uses that

The frozen-and-grow policy is working. Tests generated in round N are kept and
re-executed against the round N+1 variant, so a repair has to satisfy the whole
accumulated suite, not just the current round's tests. This is exactly what
makes the reliability judgment trustworthy: a variant cannot pass by breaking an
earlier test. The learning curve (more bugs found as rounds progress) is a direct
consequence. We should keep leaning on this; it is the mechanism behind the
"verification improves across rounds" story.

## Bug: same-named tests from different rounds collide, and one is lost

You noticed tests with the same name reappearing in later rounds, sometimes with
different logic. I confirmed it and measured it. In this single five-function
file, across four rounds, there were 10 carried-over test names, and 5 of those
were the SAME name with a DIFFERENT body. Concrete example, inclusive_range_count:

    round 0:  def test_start_greater_than_end():
                  start = 10; end = 0
                  assert inclusive_range_count(start, end) == expected_count(start, end)

    round 1:  def test_start_greater_than_end():
                  start, end = 10, 2
                  assert inclusive_range_count(start, end) == expected_count(start, end)

Same name, genuinely different inputs (10,0 versus 10,2), testing different points
in the input space. Both are useful. But the consequence was worse than a report
display issue: when the accumulated tests are stitched into one pytest module,
Python keeps only the LAST definition of a duplicated function name, so pytest
silently ran the round-1 version and never executed the round-0 version at all.
The earlier test was not just lost in the report; it was lost from the run. That
weakens the no-regression guarantee the accumulation policy is supposed to give.

## The fix (implemented)

Two parts, matching your two observations.

1. Unique test identity. Each stored test now has a `test_id` of the form
   `r{round}_{hash}`, where the hash is a short, whitespace-normalised digest of
   the test source. Identical regenerations share a hash (so they are deduplicated
   rather than stored twice), while same-name-different-logic tests get distinct
   ids and are both kept.

2. No more shadowing. When tests are concatenated for a run, each `test_*`
   function is renamed with its id suffix, for example
   `test_start_greater_than_end__r0_aa5e6de9`. Both versions now execute, and the
   pytest nodeid carries the provenance. Helper functions and call sites inside
   the test body are left untouched.

3. Provenance in results. The executor parses the suffix back out of the nodeid,
   so every TestDetail now carries `origin_round`, `test_id`, and a clean
   `display_name`. The report (and the web UI) can show the original test name
   while indicating which round each test came from, which is the round-specific
   indicator you asked for.

## What this unlocks for the thesis

The accumulation-and-no-regression property is now actually sound, not just
nominally so, which strengthens the RQ3 verified-fix argument. And because every
executed test is now tied to a round, we can show, per function, the round in
which each surviving defect-finding test first appeared. That is a clean way to
visualise "iterative feedback finds more over rounds" with the provenance to back
it.

## Note for the web UI (frontend, not in this backend PR)

The data is now present (`origin_round`, `display_name` on each TestDetail). The
remaining step is purely display: in the clickable per-round test detail, group
or badge tests by `origin_round`, for example "carried from round 1." No backend
work is needed for that; it reads the fields this change adds.
