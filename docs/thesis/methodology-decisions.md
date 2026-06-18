# Methodology decisions

A dated record of methodology decisions affecting the QALLM pipeline. Each entry captures the decision, the alternatives considered, and the reasoning. The thesis methodology chapter cites this file directly so that readers can trace which design choices were deliberate and when they were made.

## MD-001: Round 0 includes execution-based verification

**Date**: 2026-05-29

**Decision**: Round 0 (baseline) runs static analysis AND execution-based verification on the original code. No repair is applied. The result is a `ProfileVerdict` recorded as the first entry on the unit's lineage. Round 1 is judged against the round 0 baseline like any other round.

**Previous behaviour**: Round 0 ran static analysis only. Round 1 was unconditionally accepted as the first lineage entry (no parent to compare against).

**Why we changed it**:

1. **The verification-gap claim needs ground truth on the original code.** The pilot result that "91.3% of code units that pass static analysis still contain runtime defects" can only be defended if tests were actually run against the original code. Under the previous behaviour, the first execution happened after repair, so we measured "code that passes static analysis fails QALLM's tests after one repair attempt", which is a weaker claim that conflates the original with the first repair.

2. **Round 1 should be judgeable.** A repair that regresses against the original code is not "the first valid lineage entry"; it is a regression that should land in the abandoned log. Under the previous behaviour, the judge was bypassed on round 1 and any first repair was accepted regardless of quality.

3. **Uniform machinery.** Every round including round 1 now produces the same artefact bundle (`source.py`, `static.json`, `verification.json`, `profile.json`, `judge.json`, `tests/`) under `lineage/round_NN/{unit_id}/` or `abandoned/...`. Special-casing round 1 was an architectural smell.

**Alternatives considered**:

- **(a) Keep static-only baseline** (previous behaviour). Cheapest. Rejected: the verification-gap claim becomes circular.
- **(b) Analyse + verify at round 0** (adopted). Roughly +20% token budget per session. Accepted: the cost is bounded and the methodology is now defensible.
- **(c) Restructure into analyse → verify → judge → conditional repair.** Repair would happen only when tests fail. Rejected: a much larger refactor; changes the judge's role from "accept/abandon a variant" to "decide whether to repair", which moves the methodology in a direction we cannot defend before midterm.

**Cost impact**: The test-stability store treats round 0 as the test-generation round under FROZEN+REPLAY_ONLY (default). Rounds 1 onwards replay the round 0 tests. Net cost: roughly one extra verification pass per unit, not double the verification cost.

**Implementation**:
- New helper `_run_baseline_for_unit` in `orchestrator.py` constructs a synthetic `RepairedCodeUnit` where the repaired source equals the original source, then calls `verification_manager.verify(..., round_number=0)`.
- `_run_round` is simplified: the "parent is None → unconditional accept" branch is removed and replaced with an assertion. Every repair round has the baseline as parent at minimum.
- `current_round` numbering changed: starts at 0 (baseline) and advances to 1 before the repair loop.
- Reporter API unchanged: baseline goes through the same `save_round_artefacts` path with `round_number=0`, `accepted=True`, `judge_verdict_dict=None`.

**Test coverage**:
- `tests/test_orchestrator_loop.py::TestBaselineAndFirstRound` covers the new flow:
  - `test_round_0_records_baseline_without_calling_judge`: round 0 produces a lineage entry; the judge is not called for it.
  - `test_round_1_can_be_abandoned`: round 1 is now judged and can land in abandoned.
  - `test_baseline_verify_runs_against_original_source`: confirms `verify` is called on the original source with `round_number=0`.

**Implication for the pilot data**: the existing pilot numbers (91.3%, p<0.005, the round-by-round rewards) were produced under the previous behaviour. They are kept as illustrative but the full HumanEvalFix validation experiment should be re-run under MD-001 before any number is reported in the thesis. The midterm deck flags this with the "illustrative pilot averages" footnote on slide 9.

**Implication for the thesis methodology chapter**: the verification-gap framing should now read "of the code units that pass static analysis at round 0, X% have at least one execution-based test failure detected by QALLM's round 0 test suite". This is the literal, defensible form of the claim.

---

## How to add entries to this file

When a methodology decision is made, append a new section as `MD-NNN: short title` with:
1. **Date** in ISO format.
2. **Decision**: one paragraph stating what was decided.
3. **Previous behaviour**: what it replaces, if anything.
4. **Why we changed it**: the reasons that justify the change.
5. **Alternatives considered**: with brief rationale for rejection.
6. **Cost impact**: time, tokens, complexity.
7. **Implementation**: pointer to the code that implements the decision.
8. **Test coverage**: which tests demonstrate the new behaviour.
9. **Implications**: for the pilot, for the thesis chapters, for future work.

Decisions are append-only. To overturn a decision, add a new entry that explicitly references the one it overrides; do not edit the old entry.

---

## MD-002: Drop incoherent-oracle tests before execution (false-BUG prevention)

1. **Date / context**: arose from a report where a generated test fired a spurious failure: it called the function under test with `n = 1000` but compared the result against an oracle helper evaluated at `100`.

2. **Decision**: before a generated test suite is executed, deterministically remove any test whose oracle is evaluated at a different constant input than the function under test (FUT), and add a prompt rule discouraging the LLM from producing them.

3. **What it was before**: generated tests were validated only for unsatisfiable fixtures (setup errors). A test that ran but asserted against a mismatched-input oracle would fail and be counted as a BUG.

4. **Why we changed it**: this is a soundness requirement for the central claim. QALLM's contribution is that execution-based verification is a trustworthy corrective to the false confidence of static analysis. If execution itself fires on malformed oracles, the verification-gap and confirmation rates inflate with false bugs, defects attributed to the code that are actually artifacts of the test. A reported bug must be a property of the code under test, not of the test. Removing these tests keeps the bug counts (and hence all three metrics) sound.

5. **Alternatives considered**:
   - *Quarantine and flag rather than drop*: preserves more information but adds reporting surface and risk; deferred. Dropping is the conservative, easily-defended move.
   - *Try to detect wrong expected values in general*: undecidable, and would risk discarding good tests. Rejected. We flag ONLY the unambiguous constant-vs-constant input mismatch between the FUT and a module-local oracle helper.
   - *Prompt-only prevention*: necessary but not sufficient (probabilistic). Used in addition to the deterministic strip.

6. **Cost impact**: negligible; one extra AST pass per generated suite, no extra LLM calls.

7. **Implementation**: `find_incoherent_oracle_tests` / `strip_incoherent_oracle_tests` in `src/qallm/verification/test_validator.py`; wired into `TestGenerator.generate` in `src/qallm/verification/generator.py` alongside fixture stripping; prompt rule 9 in `src/qallm/verification/prompts.py`.

8. **Test coverage**: `tests/test_incoherent_oracle.py` (11 cases): flags intermediate-variable and inline mismatches; never flags same-input tests, weak assertions, unrelated production functions, non-constant inputs, or helperless suites; safe on syntax errors.

9. **Implications**: makes the bug-count denominators sound, which strengthens RQ1 (verification gap) and RQ2 (confirmation) against the examiner question "how do you know your execution-found bugs are real and not test artifacts?". The threats-to-validity section should cite this as a deliberate conservative filter. The number of tests dropped this way is itself a small reportable measure of generated-test quality.

10. **Update (metric now surfaced)**: the drop count is no longer log-only. `incoherent_oracles_dropped` (and `tests_dropped_total`) are recorded per run in `summary.json` and per session in `metrics.csv`, so the threats-to-validity argument is backed by a measured figure rather than an assertion. A low ratio of incoherent drops to tests generated is direct evidence that the generator produces sound oracles.


## MD-003: confirm/verify baseline directory naming (round_00)

**Date**: 2026-06-10

**Decision**: confirm/refute (RQ2) and verify-fixes (RQ3) read the round-0
baseline from `lineage/round_00`, resolved tolerantly (also accepting the legacy
`round_0`).

**Why**: the reporter writes zero-padded round directories (`round_{n:02d}`,
so `round_00`), but the confirm/verify reader looked only for `round_0`. On real
runs it therefore found no baseline and returned 0 confirmed / 0 refuted, which
is the most likely cause of the empty RQ2/RQ3 numbers observed on the lab set.
The unit test had used single-digit `round_0`/`round_1` fixtures, which masked
the mismatch; the fixture now uses the real naming.

**Implication**: RQ2/RQ3 should be re-run; the confirmation and verified-fix
rates that previously read as null/zero are expected to populate.


## MD-004: verification round numbering aligned to the baseline-0 convention

**Date**: 2026-06-18

**Decision**: the verification session's `RoundResult.round_number` now uses the
orchestrator's round number, where 0 is the baseline (original code, no repair)
and 1..N are improvement rounds. It previously used a session-local 1-indexed
counter, so `verification.json` labelled the baseline as "round 1".

**Why**: the orchestrator, the gap metrics, and the lineage directories all use
round 0 for the baseline (see MD-003). Only the verification session was out of
step, which made the same baseline appear as "round 0" in one artefact and
"round 1" in another. `verify()` appends exactly one `RoundResult` per
orchestrator round, so stamping it with the orchestrator round is unambiguous.
The gap runner and results reader already treated `round_number == 0` as the
baseline, so they need no change.

**Implication**: artefacts are now internally consistent on round numbering.
Any external tooling that assumed the verification session was 1-indexed should
read 0 as the baseline. The learning-curve helpers iterate rounds positionally
and are unaffected.
