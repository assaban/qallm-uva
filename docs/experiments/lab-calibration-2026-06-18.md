# Lab calibration reading: correctness oracle, 2026-06-18

Run: `runs/lab_calibration`, commit 095dd53, FedLLM gpt-oss-120b, correctness
oracle, 5 rounds, samples=1, confirm on, mutation-confidence requested. Four
sessions, one per lab file. Cost 0.00 USD. This is the instrument validation:
the lab set has a documented answer key (datasets/lab/MANIFEST.md), so these
numbers say whether QALLM measures correctly before any headline claim.

## Result against the answer key

| File | Key expectation | Measured | Verdict |
| --- | --- | --- | --- |
| reliability_gap | 5 seeded reliability bugs, all found by execution, none by static | static 0, execution-only 5 | PASS, 5/5 recall |
| clean_control | clean; at most the one known safe_mean false positive | static 0, execution-only 1 (safe_mean) | PASS, expected single FP |
| complexity_findings | complexity/maintainability findings, no runtime bug, marked not execution testable | static 1, not_execution_testable 1, but also execution-only 1 | PARTIAL, see below |
| security_findings | Bandit findings; eval and shell confirmable, build_query not | static 4, confirmed 0, inconclusive 3 | PARTIAL, see below |

## What is solid

The headline calibration claim holds: on reliability_gap, the correctness oracle
recovers all five seeded wrong-value defects (off-by-one, divide-by-max, mutable
default, None-guard, odd/even), none of which static analysis flagged and none of
which the crash oracle could ever catch because none of them throws. The failing
assertions are exact-value comparisons, for example inclusive_range_count(0,10)
returns 10 where the oracle expects 11. This is the 5/5 reliability recall that
validates the instrument, and it is the direct contrast with the earlier crash
oracle run which caught these only incidentally.

clean_control behaves as documented: a single false positive on safe_mean, where
a generated test asserts safe_mean("") returns None while the code correctly
raises TypeError on a string. The test is wrong, not the code. Its presence and
its singularity are both expected.

## Three things to fix or note before this goes in the thesis

1. Mutation confidence did not land. Every finding carries "confidence": null
   even though --mutation-confidence was set. The mutation scorer is not writing
   per-finding scores into the artefacts. Without it the gap findings cannot be
   reported high vs all confidence, which is the soundness check the thesis
   leans on. This needs a code fix before the headline run, otherwise the E1/E2
   artefacts will have the same gap.

2. complexity_findings shows an unexpected execution-only bug. The deeply_nested
   and cryptic functions are meant to be behaviourally correct (complexity is
   structural). The generated tests failed anyway, for example cryptic(5)
   returned 15 where the test expected 11, and deeply_nested(None,...) raised.
   These look like the oracle inferring a wrong specification from the function
   body, not real defects. This is exactly the weak-oracle artefact class, and
   it is why item 1 matters: with a confidence score these would likely be
   low-confidence and separable. Worth a sentence in threats to validity.

3. security_findings confirmed 0, inconclusive 3. The MANIFEST expects the eval
   and shell findings to be confirmable. Under the current run they all land
   inconclusive, which matches the documented honest position that execution
   based security confirmation is hard and out of scope, but it means the lab
   set does not currently demonstrate a positive RQ2 confirmation. State this
   as the known limit rather than a target number.

## One-line summary for section 5.1

On a labelled control the correctness oracle recovered all five seeded
reliability defects (5/5) with the single documented false positive on the clean
control; complexity and security fixtures exposed the weak-oracle and
security-inconclusive limits that the confidence layer and threats section
address.
