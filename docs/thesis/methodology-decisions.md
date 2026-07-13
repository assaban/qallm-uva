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


## MD-005: cross-evaluation, judging variants against a common final test suite

**Date**: 2026-06-18

**Decision**: add a post-hoc cross-evaluation that runs each function's *final*
accumulated test suite against *every* code variant of that function (baseline,
accepted, and abandoned). The result is a variant x test-suite matrix in which
every cell is measured against the same yardstick.

**Why**: in the live loop, round N's tests run only against round N's code
variant, so `test_pass_rate` and `bugs_caught` are computed against a different
suite for each variant. Comparing variants on those numbers is apples-to-oranges:
a variant can look stronger simply because its round generated gentler tests.
Cross-evaluation removes that confound by holding the test suite fixed across
variants, which is the sound basis for the reliability comparison the thesis
makes for RQ3.

**Evidence it works**: on the reliability_gap lab session, the baseline fails
most of the final suite (for example inclusive_range_count 4 pass / 20 fail)
while the repaired variant passes nearly all of it (23 pass / 1 fail), and the
*abandoned* normalise_unit variant is measurably worse under the common suite
(16 failures) than the accepted one (7 failures). The latter independently
corroborates the judge's decision to abandon it, using a comparison the live
loop could not make.

**Scope and safety**: read-only and post-hoc. It reads the persisted source.py
and tests/ artefacts and does not change the live judging path, so existing
behaviour and tests are unaffected. It is exposed at
`GET /api/session/{id}/cross-evaluation` for the comparison-table UI.

**Implication for the thesis**: the RQ3 verified-fix argument can now cite a
common-yardstick comparison rather than per-round suites, and the abandoned-vs-
accepted contrast is a concrete demonstration that the judge's decisions hold up
under a fairer test. A limitation to state: the final suite is itself generated,
so it is the strongest suite the session produced, not an external ground truth;
on the labelled set it can be cross-checked against the answer key.


## MD-006: RQ2 confirmation reframed for reliability via the gap defects

**Date**: 2026-06-20

**Decision**: confirmation (RQ2) for reliability is derived from the
execution-only gap defects, not from static findings. Each execution-only defect,
a function whose generated correctness test failed against the original code, is
recorded as a confirmed RELIABILITY defect, with that failing test as its
reproducing test. RQ3 (verified-fix) then re-runs each such test against the
repaired code; a pass means the defect is fixed. Static-finding confirmation is
retained and reported separately (confirmed_static), and remains inconclusive for
security by design.

**Why**: the E2 run (2026-06-20, confirm on) returned confirmed = 0 across the
whole ENVRI corpus. The cause is not a bug in the run: the static analysers emit
SECURITY, COMPLEXITY, and MAINTAINABILITY findings, never RELIABILITY. So the
static-finding confirm path can only ever adjudicate SECURITY findings, which are
inconclusive without a demonstrated exploit (the documented security-scope
limit). The reliability defects that are the heart of the verification gap have
no static finding for that path to confirm, because static analysis missing them
is the entire premise of the gap. Confirming them therefore has to come from the
execution evidence itself, which the gap pipeline already produces.

**Why this is sound, not circular**: a gap defect is confirmed by a correctness
test that asserts the specification (derived from the signature and docstring,
never the body, see MD on the correctness oracle) and fails on the original code.
That is independent evidence of a real defect, the same standard the static-
finding path uses (a targeted test that reproduces the finding). The reframe
applies that standard to the defects execution found rather than only to the
findings static analysis raised.

**Evidence**: on the reliability_gap lab session the reframe yields 5 confirmed
reliability defects (was 0) and a verified-fix rate of 4/5 = 0.8. The one
not-fixed (accumulate) is a true negative: its reproducing test still fails on
the repaired variant, which the cross-evaluation independently corroborates.

**Implication for the thesis**: RQ2 is reported as two confirmation sources kept
distinct: reliability confirmation from the gap defects (a real, non-trivial
count and rate), and static-finding confirmation (security, inconclusive by
design). RQ3 follows from the reliability confirmations. State the framing
explicitly so the confirmation rate is not mistaken for static-finding
corroboration.

## MD-007: E2 headline reporting: dual weighting, counts for RQ2, and the truncation lesson

**Date**: 2026-07-10

**Decision**: The E2 (full ENVRI forest corpus) results are reported as follows.

1. **RQ1 headline is the count-weighted gap rate with a bootstrap CI**: 732 execution-only defects over 4,298 verified functions, 17.0% (95% CI [14.7%, 19.6%], session-resample). It is always accompanied by the project-weighted view (macro average 21.2%, median 11.1%, IQR [0%, 35%] over the 112 projects with at least five verified functions) and a dominant-project sensitivity check: `sentinel-tree-cover` alone contributes 22% of the denominator at a 1.1% gap rate; excluding it the count-weighted rate is 21.6%. One number without the other two invites either overstatement (ignoring the well-engineered outlier) or understatement (letting one repository speak for 285 projects).

2. **RQ2 is reported as counts, never as a confirmation rate**: 747 confirmed reliability defects, each with a persisted reproducing test; 265 static findings inconclusive (security is inconclusive by design); 0 refuted. Refutation is structurally near-impossible (MD-006), so confirmed/(confirmed+refuted) is 100% by construction and must not appear as a statistic.

3. **RQ3**: verified-fix rate 58.4% (391/669, 95% CI [53.1%, 63.9%]), count-weighted; it is stable across corpus composition (58.1% in the first 1,376 sessions, 58.4% final), unlike the gap rate.

4. **The truncation lesson is documented, not hidden**: the 75%-complete partial showed a 24.6% gap rate; the completed corpus shows 17.0%. The resumed tail was 42 previously untouched projects processed in discovery order, including the dominant low-gap repository. This validates the standing rule that partial results from non-random truncation must not be reported as final, and it goes in the threats-to-validity section as a worked example.

**Why**: corpus skew is a fact of harvested notebook corpora, and examiners will probe any single-number headline. Reporting all three RQ1 views with an explicit sensitivity check converts the skew from a vulnerability into evidence of care.

**Implementation**: `scripts/analyze_gap_results.py` recomputes every reported number from `results.jsonl` and writes `analysis.json`/`analysis.md` into the run directory. All thesis numbers come from that script, not from hand computation.

## MD-008: Aggregate roll-up corrections and the E2 resume provenance note

**Date**: 2026-07-10

**Decision**: two aggregate bugs found via the E2 final artifacts are fixed, and the E2 provenance split is recorded.

1. **Degenerate aggregate gap rate**: `AggregateMetrics.verification_gap_rate` divided execution-only defects by (confirmed findings + execution-only), which is 1.0 whenever confirmed static findings are zero, the normal case per MD-006. The denominator is now `total_functions_verified`, matching the per-session definition, and the bootstrap CI pairs follow. `aggregate.json` files written before this fix carry the degenerate value; `results.jsonl` rows were always correct, and `scripts/analyze_gap_results.py` recomputes from rows.

2. **RQ2 split lost on resume**: `_metrics_from_dict`, the path that re-reads prior rows when a run resumes, omitted `confirmed_static` and `confirmed_reliability_gap`, so any resumed run reported zeros for the split while `total_confirmed` was correct. Both fields now round-trip. Regression tests: `tests/test_aggregate_gap_rate.py`.

3. **Provenance note for E2**: the run spans two commits. Sessions before the disk-space interruption ran at `064ddc7`; the resumed tail and the manifest's recorded provenance are at `c7c0581`. The only source change between the two is `src/qallm/experiments/humaneval_metrics.py` (plus docs, CI, and its own test), which the gap pipeline does not import. The run is therefore behaviorally single-version for every executed code path; the thesis reproducibility statement says exactly this rather than hiding the split.

## MD-009: Benchmark statistics are McNemar exact; the anchoring result scopes the claim

**Date**: 2026-07-12

**Decision**: two decisions from the completed HumanEvalFix pair.

1. **Paired binary outcomes use McNemar's exact test**, not the Wilcoxon
signed-rank named in early planning. Detection and repair are binary per
problem and paired per problem across conditions; Wilcoxon degenerates on
paired binary data, while McNemar on the discordant pairs is the standard
correct test, exact form because discordant counts are small. The thesis
states the substitution and the reason in one clause (tab:ablation caption
and sec:benchmark).

2. **The benchmark's detection floor is reported as a scoping result, not
softened.** Detection stays at 1.8 to 4.9% under both oracles while repair
doubles significantly under the matched oracle within every strategy
(p <= 0.007). The mechanism consistent with both is implementation
anchoring. Consequence, claimed explicitly: QALLM detects reliability
defects, code violating its own contract on plausible inputs, and does not
solve detection of subtle semantic divergence from an external
specification without ground truth. The corpus headline and the benchmark
floor are therefore complementary measurements of one instrument, not a
contradiction.

**Record**: full numbers in
`docs/experiments/heval-correctness-final-2026-07-11.md`; both run
directories are pinned.

## MD-010: The .py arm samples authored analysis code only

**Date**: 2026-07-12

**Decision**: the notebook-vs-python form comparison (playbook run 4)
excludes test files (`*/tests/*`, `*/test/*`, `test_*.py`, `*_test.py`,
`conftest.py`), `__init__.py`, `setup.py`, and Sphinx `conf.py` from the
.py sampling frame, via the runner's new `--exclude` globs.

**Why**: the form comparison isolates one variable, the code form. The raw
.py trees are 45% test files and boilerplate that have no notebook
counterpart; sampling them would compare notebooks against a different
population, not a different form. Exclusion patterns are recorded in the
run manifest because they change the sampling frame: a manifest without
them could not reproduce the sample. The notebook arm needs no equivalent
list; the runner's built-in cruft filter (checkpoints, backups, sidecars)
already covers its known contaminants and applies to both arms.

**Implementation**: `--exclude GLOB` (repeatable) on
`scripts/run_gap_experiment.py`, matched against the dataset-relative path
and the bare filename; regression tests in
`tests/test_discovery_excludes.py`.
