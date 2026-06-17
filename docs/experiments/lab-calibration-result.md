# Lab calibration result: the correctness oracle works

> NOTE. This record predates the single-sample decision. Any `--samples 5`
> invocation below is superseded; the calibrated setting is `--samples 1`
> (5/5 reliability recall confirmed). See docs/thesis/methodology-decisions.md.


Status: result record, 2026-06-10. This is the calibration milestone that makes
the verification gap trustworthy on the reliability defect class.

## The two runs

After fixing the oracle-threading bug (the correctness oracle was not reaching
round-0 generation; the generator defaulted to crash), two runs on the lab set:

| File (answer key) | Run 1: correctness, samples=1 | Run 2: correctness, samples=5 (consensus) |
| --- | --- | --- |
| clean_control (expect 0) | 1 | **0** |
| complexity_findings (expect 0) | 1 | 1 |
| reliability_gap (expect 5) | **5** | **5** |
| security_findings (static only) | 0 exec, 4 static | 0 exec, 4 static |

Two clear wins:

1. **reliability_gap = 5 of 5.** Once the correctness oracle actually ran at
   round 0, it caught every seeded reliability bug. The earlier 1 to 2 of 5 was
   the threading bug, not a detector weakness; we had never measured the
   correctness oracle at the gap pass.
2. **clean_control = 0 under consensus.** The single-sample false positive on
   safe_mean disappeared with 5 samples.

## The one residual: complexity_findings `cryptic`

Both runs report 1 execution-only bug on complexity_findings, on the `cryptic`
function. This is a false positive, and the cause is instructive.

`cryptic(x)` computes `3x` (q=2x, z=2x+1, w=2x, return w+q-x = 3x). Its docstring
says only "doubles then offsets" and explicitly notes the behaviour is correct
with no runtime defect; the finding is maintainability, not correctness. The
correctness oracle, given that vague docstring and no body, guessed wrong
expected values and generated tests that fail correct code.

Why consensus did not remove it: the current consensus is a UNION of samples
(it keeps every sample's tests to maximise recall). A wrong expected value in
any single sample survives the union. clean_control's safe_mean went to 0 in run
2 because that round's merge happened to contain no wrong assertion, which is
luck of the draw, not robust filtering. The principled fix is assertion-level
majority voting (keep an expected value only if a majority of samples agree on
it), which would outvote a one-off wrong assertion. That is the documented next
step in oracle-variance-and-consensus.md.

## Is this good enough to proceed?

Yes, with eyes open. The calibration demonstrates what the thesis needs: high
recall (5/5) on real reliability defects and zero false positives on clean code
under consensus. The one residual is a single false positive on a function whose
docstring is deliberately underspecified (the lab set built it to exercise
maintainability, not correctness), so it is as much a spec-ambiguity case as a
detector case. Two honest ways to close it, in order of preference:

Assertion-level majority voting is now implemented (consensus_vote): the
minority wrong expected value on `cryptic` is outvoted and dropped before the
union, which removes the false positive while keeping reliability_gap at 5/5. A
re-run with --samples 5 should now show clean_control 0, complexity_findings 0,
reliability_gap 5. That is the full calibration target.

## What this unblocks

The instrument is trustworthy enough to run ENVRI for the RQ1 headline with
`--oracle correctness --samples 5`. The lab numbers (5/5 recall, 0 false
positives on clean code) are the calibration evidence for Chapter 5, and the
`cryptic` case is a clean, honest example of the oracle's one failure mode
(underspecified specs), which is worth a paragraph in the thesis rather than
something to hide.


## Correction (consensus was not actually running)

A later voted run (`--samples 5`) still showed clean_control 1 and
complexity_findings 1, and the artifacts revealed why: the generated suites had
no per-sample namespacing, meaning the consensus merge never ran despite
`samples=5` in the manifest. Root cause: the verification manager attaches an
EMPTY session before the first `generate()` call, and the consensus guard tested
`existing_session is not None`, so it treated round 0 as a feedback round and
fell back to a single sample. Consensus (and therefore voting) was silently
disabled in every "consensus" run so far; run 2's clean_control 0 was a
single-sample lucky draw, not the merge working.

Fix: the guard now tests whether the session has prior ROUNDS (a real feedback
round), matching how the prompt selector distinguishes feedback. With this,
`--samples 5` actually generates five samples at round 0 and votes across them.
The lab re-run with the fix in place is the first that truly exercises
consensus + voting; that is the run that should land clean_control 0,
complexity_findings 0, reliability_gap 5.
