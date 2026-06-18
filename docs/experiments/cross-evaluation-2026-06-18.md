# Cross-evaluation: judging every variant by the same final test suite

This note records the first cross-evaluation result and what it shows. The
method is described in MD-005.

## The problem it solves

In the live loop, round N's accumulated tests run only against round N's code
variant. So the reliability numbers the judge compares (test_pass_rate,
bugs_caught) are each measured against a different test suite. A variant can
look stronger merely because its round generated gentler tests. That is not a
sound basis for comparing variants.

Cross-evaluation holds the suite fixed: it assembles each function's final
accumulated suite and runs it against every variant (baseline, accepted, and
abandoned). Every cell is then measured against the same yardstick.

## First result (reliability_gap lab session)

Final suite versus every variant, pass / fail counts:

| Function | round 0 (baseline) | round 1 (accepted) | round 2 (abandoned) | round 4 (accepted) |
| --- | --- | --- | --- | --- |
| inclusive_range_count | 4 / 20 | 23 / 1 | 23 / 1 | 23 / 1 |
| first_even | 5 / 22 | 25 / 2 | 25 / 2 | 25 / 2 |
| normalise_unit | 6 / 23 | 22 / 7 | 13 / 16 | 22 / 7 |
| safe_divide | 18 / 8 | 25 / 1 | 25 / 1 | 25 / 1 |
| accumulate | 10 / 13 | 18 / 5 | 10 / 13 | 18 / 5 |

## What it shows

1. Repair works, measured fairly. Every function improves sharply from the
   baseline to the accepted variant under the same suite: inclusive_range_count
   goes from 4 pass / 20 fail to 23 / 1, first_even from 5 / 22 to 25 / 2. This
   is the verification-gap repair demonstrated on a common yardstick, not on
   per-round suites.

2. The judge's abandon decisions hold up. normalise_unit round 2 was abandoned
   by the judge. Under the common suite it is measurably worse (13 pass / 16
   fail) than the accepted round-1 variant (22 / 7). accumulate round 2 is
   likewise back at baseline level (10 / 13). The judge rejected variants that a
   fair, fixed test suite also rejects, which independently corroborates the
   lexicographic judge using a comparison the live loop could not make.

## For the thesis

This supports RQ3 (verified fixes) with a common-yardstick comparison and gives
a concrete, defensible answer to "how do you know an accepted variant is really
better than an abandoned one?". State the limitation honestly: the final suite
is generated, so it is the strongest suite the session produced rather than an
external ground truth; on the labelled lab set it can be cross-checked against
the MANIFEST answer key.
