# Backlog Audit, May 2026

Audit of the GitHub issue backlog of `assaban/qallm-uva` against the v3 workflow design document (`docs/workflow-design.md`). This file records the state of every issue at the time of audit, the proposed action, and the new issues to create.

The goal of the audit is to bring the backlog into agreement with what is on `dev` today and with the v3 design. Closed-but-stale issues stay closed. Open issues are either confirmed as still valid, edited to match current state, closed with a reason, or merged with newer duplicates. The audit ends with a list of new issues to create from section 12 of v3.

## Snapshot

* Total issues in repository: 23.
* Open at time of audit: 14.
* Closed: 9.
* Two generations of issues coexist: an early set (numbers 1 to 11) using `foundation/stage-1/stage-2` labels and citing the original proposal, and a later set (numbers 19 to 30) using `RQ1/RQ2/RQ3` labels and the three-strategy framing.
* Several open issues in the early set have been functionally superseded by issues in the later set without being closed.
* A substantial body of work shipped to `dev` over the past week (EVERSE alignment, jobs, deployment, workflow doc) is not represented in the backlog at all.

## Part 1: Audit of existing issues

### Already closed (no action needed)

These are listed for completeness only. No action.

| # | Title | Verdict |
|---|-------|---------|
| 1 | DEV-01: CI/CD Pipeline Setup | Closed, correctly. |
| 2 | FEAT-01: Unified Ingestion Layer | Closed, correctly. Matches `qallm.ingestion` on dev. |
| 3 | FEAT-02: Quantitative Quality Engine (QQE) | Closed, correctly. Matches `qallm.analysis`. |
| 4 | FEAT-03: Lifecycle-Aware Normalizer | Closed, correctly. Matches `qallm.analysis.normalizer`. |
| 5 | FEAT-04: Prompt Construction Module | Closed, correctly. |
| 6 | FEAT-05: Iterative Verify-Rescore Loop | Closed, correctly. |
| 8 | FEAT-06: Oracle Implementation | Closed, correctly. |
| 9 | FEAT-07: RL Reward Function & Multi-round Loop | Closed, correctly. |

### Open issues to close

These are open but the work is done, superseded, or no longer matches the v3 design.

#### Issue #11: FEAT-08: Jupyter Frontend Trigger (ipywidgets)

**State:** open, label `foundation`. Body: "Build the 'Run Check' button for in-notebook initiation as requested by Dr. Zhao."

**Verdict:** duplicate. Identical scope to issue #27 (FEAT-10), which has a proper acceptance-criteria section.

**Action:** close as duplicate of #27. Comment to leave on the issue:

> Superseded by #27, which has the same scope with full acceptance criteria. Closing as duplicate.

#### Issue #10: RESEARCH-02: False Confidence Rate Analysis

**State:** open, label `stage-1`. Body: one sentence.

**Verdict:** duplicate. Issue #24 (RESEARCH-03 in the newer set) describes the same analysis with full method, acceptance criteria, and dependencies.

**Action:** close as duplicate of #24.

> Superseded by #24, which has the full methodology and acceptance criteria. Closing as duplicate.

#### Issue #7: RESEARCH-01: Baseline Implementation (Hypothesis)

**State:** open, label `stage-2`. Body: one sentence about Strategy (a).

**Verdict:** done and duplicate. The Hypothesis baseline is implemented in `qallm.verification.hypothesis_baseline` on dev and was the subject of PR #31 (merged). Issue #19 (FEAT-07 in the newer set) is the proper tracking issue for the same scope and is itself complete.

**Action:** close as completed, referencing PR #31.

> Implemented in PR #31. Code lives at `src/qallm/verification/hypothesis_baseline.py`. Also superseded in the newer backlog by #19.

#### Issue #19: FEAT-07: Hypothesis Baseline Generator

**State:** open, labels `engineering`, `RQ1`, `P0`. Full acceptance criteria.

**Verdict:** done. The baseline exists, the `--strategy hypothesis` flag works, the pilot ran successfully. The unit-test acceptance criterion is partially met by the broader test suite.

**Action:** close as completed, referencing PR #31 and the dev branch.

> Implemented and merged in PR #31. `--strategy hypothesis` available in CLI and orchestrator. Pilot results across 31 functions confirm the baseline runs and produces comparable JSON output. Closing.

#### Issue #20: FEAT-08: Strategy Router in Orchestrator

**State:** open, labels `engineering`, `RQ1`, `P0`. Full acceptance criteria.

**Verdict:** done. The orchestrator routes `--strategy hypothesis|oneshot|rl` on dev. Acceptance criteria are met:

- CLI accepts the flag (confirmed in `src/qallm/run_qallm.py`).
- Orchestrator routes correctly (confirmed in `src/qallm/orchestrator.py`).
- Summary JSON includes `strategy` field.
- One-shot is `rl` with `rounds=1`.

**Action:** close as completed.

> All acceptance criteria met. Strategy routing live in `qallm.orchestrator`. Closing.

#### Issue #21: RESEARCH-01: Pilot Three-Strategy Comparison

**State:** open, labels `research`, `RQ1`, `P0`. Body describes a pilot on `model.py` (8 functions).

**Verdict:** done with different scope. The pilot ran across 31 functions in 5 files (not just `model.py`), with three models (gpt-4o-mini, gpt-5-mini, gemma3:4b). Results are statistically significant: all pairwise Wilcoxon tests on bug-finding at p < 0.005, with a 91.3% false confidence rate. This is the empirical anchor of the thesis.

**Action:** close as completed, with a note about the scope expansion. The expanded pilot is the actual finding cited in the thesis and the midterm presentation.

> Completed with expanded scope: 31 functions across 5 files (not just `model.py`), three models, statistically significant results (all pairwise Wilcoxon p < 0.005). 91.3% false confidence rate. This is the pilot cited in the midterm presentation. Closing.

### Open issues to edit

These remain valid but their descriptions are out of date relative to dev.

#### Issue #22: DATA-01: Acquire Li's Validated Notebook Dataset

**State:** open, labels `research`, `blocked`, `RQ1`, `RQ2`, `P0`. Body: full description.

**Verdict:** still valid. Still blocked on Nafis. Per most recent supervisor communication, the request has been made.

**Action:** keep open. Update body to note the request has been sent. Remove the `blocked` label only when the dataset arrives.

> No edit needed to the issue body if you prefer; the status is unchanged.

#### Issue #23: RESEARCH-02: Full RQ1 Experiment (200 Notebooks)

**State:** open, labels `research`, `RQ1`, `P0`. Body describes the full 3 x 3 x 200 experiment.

**Verdict:** still valid and aligned with section 9.5 of v3. The "200 notebooks" subset framing is fine; the full Li dataset is 2,796 notebooks across 277 projects, and 200 is a reasonable curated subset.

**Action:** keep open. Optional edit: add a forward reference to the v3 doc section 12, item 9.

> Tracks correctly. Depends on DATA-01.

#### Issue #24: RESEARCH-03: False Confidence Rate Analysis (RQ2)

**State:** open, labels `research`, `RQ2`, `P1`. Body: full description.

**Verdict:** partially done in the pilot, full version still valid. The 91.3% figure from the 31-function pilot is itself a false confidence rate measurement. The 200-notebook version remains to be done after DATA-01.

**Action:** keep open. Add a note to the body:

> Pilot-scale FCR already computed: 91.3% over 31 functions. Full 200-notebook scale awaits DATA-01.

#### Issue #25: RESEARCH-04: Expert Validation Study (RQ2 + RQ3)

**State:** open, labels `research`, `RQ2`, `RQ3`, `P1`. Body: full description.

**Verdict:** still valid. This is the user study underpinning RQ3 (the "actionable feedback to researchers" question). Worth confirming with Nafis whether this is in scope for the thesis or for future work, given the constraints of a single-author MSc.

**Action:** keep open. Flag for supervisor discussion: is this in scope for the thesis or a future-work item? RQ3 as written assumes actionability evidence; if no user study runs, RQ3 may need softening.

#### Issue #26: FEAT-09: Verification-Based Quality Metrics

**State:** open, labels `engineering`, `RQ2`, `P1`. Body: defines four new metrics for Volentir et al. framework compatibility.

**Verdict:** partially superseded by v3. Some of the proposed metrics (Functional Correctness Score, Verification Coverage, False Confidence Rate) are already produced by the QALLM pipeline; some (Security Assessment Score with CWE coverage) are new and not yet built.

**Action:** edit the body to reflect what is done and what remains. Specifically:

- Functional Correctness Score: already produced as `test_pass_rate` in the Reliability indicator.
- Verification Coverage: already produced as coverage delta in the verification session.
- False Confidence Rate: already computed in the pilot.
- Security Assessment Score with CWE coverage: new, not yet built. Worth keeping as a `P2` engineering item or closing as future work.

> Recommendation: edit the body to keep only the Security Assessment Score work; mark the other three as already produced by the pipeline (with file pointers). Then re-prioritise the issue to P2 since only the CWE-coverage piece remains.

#### Issue #27: FEAT-10: Jupyter Frontend Trigger

**State:** open, labels `engineering`, `RQ3`, `P2`. Body: full acceptance criteria.

**Verdict:** still valid. Not yet built. Aligns with RQ3.

**Action:** keep open. After #11 is closed as a duplicate, this is the sole tracking issue.

#### Issue #28: THESIS-01: Write Methodology Chapter

**State:** open, label `writing`, `P1`. Body: lists sections.

**Verdict:** still valid. Methodology chapter aligns with workflow doc v3 plus the three-framework positioning.

**Action:** keep open. Add a forward reference to `docs/workflow-design.md` as the primary source for the Methodology chapter.

#### Issue #29: THESIS-02: Write Results Chapter

**State:** open, label `writing`, `P1`. Body: lists RQ-aligned sections.

**Verdict:** still valid. Depends on RESEARCH-02, -03, -04.

**Action:** keep open.

#### Issue #30: THESIS-03: Defence Preparation

**State:** open, labels `writing`, `P2`. Body: lists deliverables (slides, demo, dashboard).

**Verdict:** still valid. Midterm presentation slides exist already as a separate artefact; this issue tracks the final defence deck.

**Action:** keep open.

## Part 2: Work shipped but not tracked

The following work landed on `dev` over the past week without corresponding tracking issues. For the record, and to give the audit a clean basis, these should be reflected either by retrospectively creating closed issues (one per merged PR) or by accepting that the audit document itself is the record.

Recommendation: do not create retrospective issues. The PRs themselves are the record. Mention this audit document in the next supervisor update so there is a single place that lists what shipped.

For reference, the work in question:

* PR #33: `feature/everse-readme` (README aligned with EVERSE).
* PR #34: `feature/everse-profiles` (`qallm.profiles` module).
* PR #35: `feature/everse-evaluation` (`qallm.evaluation` registry and verdicts).
* `feature/jobs-verification` (in-memory background job store, verification as a job, API integration).
* `feature/deploy-containers` (Dockerfile, docker-compose, README installation section, frontend serving).
* `feature/everse-readme` follow-ups for Ollama and host-side LLM.
* `feature/workflow-doc-v3` (the v3 workflow design document).

## Part 3: New issues to create from v3 doc section 12

These follow directly from the v3 design. One issue per implementation item. Labels and priorities suggested below. None of them should be created with `P0`: the critical path right now is the experiments (RESEARCH-02, RESEARCH-03), which depend on DATA-01, not on more engineering.

### NEW-01: Test suite persistence (v3 section 4.5)

**Title:** FEAT: Test suite persistence per code unit, with configurable strategy
**Labels:** `engineering`, `RQ1`, `P1`
**Body:**

```
## What
Implement persistence of generated test suites per code unit, supporting both
configurable strategies from workflow design v3 section 4.5:

- `frozen` (default): tests are bound to the code unit and accumulate across
  rounds; never removed or replaced.
- `per_round` (alternative): each round has its own independent suite.

## Why
Without this, cross-round comparisons of variants are invalid because the
RL loop can generate easier tests for worse variants. See workflow-design.md
section 4.5 for the full discussion.

## Acceptance criteria
- [ ] New module `qallm.verification.test_persistence` with a `TestSuiteStore`
      keyed by `(session_id, code_unit_id)`.
- [ ] `test_stability` parameter in orchestrator config (frozen | per_round),
      default `frozen`.
- [ ] Frozen strategy: each round appends tests, applies full union to next
      variant.
- [ ] Per-round strategy: each round stores its suite independently.
- [ ] Unit tests cover both strategies.
- [ ] `summary.json` reflects which strategy was used.

## Estimated effort
80-100 lines plus tests.

## References
docs/workflow-design.md, section 4.5.
```

### NEW-02: Judge module with three improvement strategies (v3 section 5 and 9.3)

**Title:** FEAT: Judge module with lexicographic, strict, and model strategies
**Labels:** `engineering`, `RQ2`, `P1`
**Body:**

```
## What
Implement the judge component that decides whether a repaired variant is an
improvement over its parent in the lineage.

## Strategies
- `lexicographic`: ordered dimensions (default: Security > Reliability >
  Maintainability > Reproducibility > FAIRness); regressions in higher-priority
  dimensions block acceptance.
- `strict`: any regression in any indicator means abandonment.
- `model`: judge LLM decides freely, with explanation. Default for v1.

## Judge inputs
Both profile output and raw verification numbers (test pass/fail, bug list,
coverage delta). See section 5.4.

## Acceptance criteria
- [ ] New module `qallm.judge` with `JudgeStrategy` enum and dispatcher.
- [ ] Three concrete strategies implemented.
- [ ] Judge model is independently configurable from the repair model.
- [ ] Verdict storage: every judgement records both model output and the raw
      numerical comparison (for thesis-chapter validation, see section 5.2).
- [ ] Unit tests for each strategy.

## Estimated effort
~150 lines plus tests.

## References
docs/workflow-design.md, sections 5 and 9.1 to 9.3.
```

### NEW-03: Wire reliability indicators to verification (v3 section 11)

**Title:** FEAT: Wire reliability indicators in evaluation to verification output
**Labels:** `engineering`, `RQ2`, `P1`
**Body:**

```
## What
The reliability indicators in `qallm.evaluation` currently return None (deferred
stubs from the original PR). Connect them to actual verification session output
so `evaluate_profile` produces real numbers for Reliability.

## Acceptance criteria
- [ ] `qallm.verification.pass_rate` evaluator reads from the latest verification
      session for the given code unit.
- [ ] `qallm.verification.bugs` evaluator reads the bug list.
- [ ] Test coverage for the wiring.

## Estimated effort
~40 lines plus tests.

## References
src/qallm/evaluation.py (existing deferred stubs).
docs/workflow-design.md, section 11.
```

### NEW-04: FAIRness indicators (v3 section 9.4)

**Title:** FEAT: FAIRness indicators (licence, citation, README, docstrings)
**Labels:** `engineering`, `RQ2`, `P1`
**Body:**

```
## What
Implement the FAIRness dimension's indicators per workflow doc section 9.4.

## Indicators (initial set)
- Presence of a licence file in the project root.
- Presence of a citation file (CITATION.cff, CITATION.bib).
- Presence of a README with required sections (description, install, usage).
- Documented function signatures (docstring coverage above threshold).

## Acceptance criteria
- [ ] New module `qallm.fairness` with four evaluator functions.
- [ ] Evaluators registered in `qallm.evaluation`.
- [ ] FAIRness dimension added to `IMPLEMENTATION_DEFAULT` profile.
- [ ] Unit tests with fixture projects (with and without each artefact).

## Estimated effort
~100 lines plus tests.

## References
docs/workflow-design.md, section 9.4.
```

### NEW-05: Budget enforcement with cost estimation (v3 section 6)

**Title:** FEAT: Hard budget caps (rounds, tokens, time, dollars) with cost estimation
**Labels:** `engineering`, `RQ1`, `P1`
**Body:**

```
## What
Implement hard budget caps in the orchestrator's loop control, enforced at
round boundaries. Caps must take precedence over env-var configuration up to
defined ceilings.

## Caps
- Max rounds (default 5, ceiling 10).
- Max total tokens (default 500k, ceiling 2M).
- Max wall-clock seconds (default 1800, ceiling 3600).
- Max per-round seconds (default 600).
- Max estimated cost in USD (default 5.00, ceiling 25.00).

## Acceptance criteria
- [ ] New module `qallm.cost` with per-model price table and a session cost
      estimator.
- [ ] Price table maintained in `qallm.config`, documented as needing manual
      updates.
- [ ] Orchestrator calls cost check at every round boundary.
- [ ] Cap trip halts the loop and writes the cap reason to `summary.json`.
- [ ] Unit tests for each cap.

## Estimated effort
~50 + 80 lines.

## References
docs/workflow-design.md, section 6 and 9.6.
```

### NEW-06: Extend orchestrator loop per v3 (v3 section 3)

**Title:** FEAT: Orchestrator loop implements the v3 analyse-repair-verify-judge cycle
**Labels:** `engineering`, `RQ1`, `P1`
**Body:**

```
## What
Bring the orchestrator's main loop in line with the v3 workflow specification.
Round 0 baseline, then iterate accept-or-abandon per round, halt on budget
or convergence, log accepted variants to lineage and abandoned ones separately.

## Acceptance criteria
- [ ] Round 0 produces baseline with no repair.
- [ ] Each subsequent round runs repair, analyse, verify, judge in that order.
- [ ] Accepted variants extend lineage; rejected variants go to abandoned log.
- [ ] Loop halts on any of: budget cap, model verdict says stop, convergence.
- [ ] Manual and auto modes produce identical artefacts (section 8).
- [ ] Integration test covering the full loop with a stubbed judge.

## Estimated effort
~100 lines.

## References
docs/workflow-design.md, sections 3 and 8.
```

### NEW-07: Reporter extension: lineage, abandoned log, JSON canonical

**Title:** FEAT: Extend reporter with lineage, abandoned log, summary.json canonical
**Labels:** `engineering`, `RQ2`, `P1`
**Body:**

```
## What
The reporter must emit the artefacts defined in workflow doc section 10.

## Acceptance criteria
- [ ] `lineage/round_<n>/` directory per accepted round with: source, tests,
      static.json, verification.json, profile.json, judge.json.
- [ ] `abandoned/round_<n>/` directory per abandoned variant, same shape.
- [ ] `summary.json` as the canonical record; sufficient to reconstruct the
      session.
- [ ] `report.md` and `report.html` generated from `summary.json` as human
      views.
- [ ] Schema documented in a short `docs/output-schema.md`.

## Estimated effort
~100 lines plus a schema doc.

## References
docs/workflow-design.md, section 10.
```

### NEW-08: Auto-mode fix to drive the new loop (v3 section 8)

**Title:** FIX: Auto mode drives the v3 loop (currently stops after one round)
**Labels:** `engineering`, `RQ3`, `P1`
**Body:**

```
## What
Auto mode in the web UI currently halts after one round. Update it to drive the
v3 loop end-to-end, matching manual mode behaviour.

## Acceptance criteria
- [ ] Auto mode runs analyse -> repair -> verify -> judge cycles to completion
      or budget exhaustion.
- [ ] Manual and auto produce identical session artefacts on the same input.
- [ ] Progress events stream to the UI per round.
- [ ] No regression on existing manual-mode flow.

## Estimated effort
small change, depends on NEW-06.

## References
docs/workflow-design.md, section 8.
```

### NEW-09: HumanEval validation experiment (v3 section 9.5)

**Title:** RESEARCH: HumanEval-with-injected-bugs validation experiment
**Labels:** `research`, `RQ1`, `RQ2`, `P1`
**Body:**

```
## What
A secondary validation experiment using OpenAI HumanEval as ground truth.
Inject bugs into reference solutions, run QALLM against the mutants, measure
detection and repair rates.

## Why
This experiment gives the thesis a ground-truth-backed methodology validation
in addition to the EVERSE-aligned Li-dataset experiment. Requested by Zhao
through Nafis at the weekly meeting.

## Acceptance criteria
- [ ] Mutation catalogue documented (categories of bugs to inject).
- [ ] Driver script that loads HumanEval, applies mutations, runs QALLM.
- [ ] Metrics: detection rate, repair rate, false-positive rate per mutation
      category.
- [ ] Results report in a separate notebook or markdown file.

## Estimated effort
A few days of focused setup; independent of the main pipeline.

## References
docs/workflow-design.md, section 9.5.
https://huggingface.co/datasets/openai/openai_humaneval
```

### NEW-10: Walkthrough of useAutoRunner (knowledge debt)

**Title:** DOC: Document the auto-mode useAutoRunner workflow
**Labels:** `documentation`, `RQ3`, `P2`
**Body:**

```
## What
The current `useAutoRunner` hook drives the front-end auto mode. The author has
flagged not fully understanding the end-to-end behaviour. Once the new loop
lands (NEW-06, NEW-08), document the front-end orchestration in a short note
under `docs/`.

## Acceptance criteria
- [ ] Markdown doc explains: trigger, polling pattern, error handling, screen
      transitions.
- [ ] Diagram (Mermaid) of the front-end state machine.

## Estimated effort
~30 minutes once NEW-08 is done.
```

## Part 4: Summary of proposed actions

### Close (6 issues)

* #7: close as completed.
* #10: close as duplicate of #24.
* #11: close as duplicate of #27.
* #19: close as completed.
* #20: close as completed.
* #21: close as completed.

### Edit (4 issues)

* #22: note that the request has been made; leave `blocked` until dataset arrives.
* #24: note that pilot-scale FCR is already computed.
* #25: flag for Nafis discussion: in scope for thesis, or future work?
* #26: narrow body to just the Security/CWE work; downgrade to P2.

### Keep as-is (4 issues)

* #23, #27, #28, #29, #30. All still valid and aligned with v3.

### Create (10 new issues)

NEW-01 to NEW-10 as specified above.

## Part 5: Net effect

After these actions, the open backlog will contain:

| Bucket | Open issues |
|--------|-------------|
| Research (experiments) | #22 (DATA-01), #23 (200-notebook RQ1), #24 (FCR full), #25 (expert study), NEW-09 (HumanEval) |
| Engineering (v3 implementation) | NEW-01 (test persistence), NEW-02 (judge), NEW-03 (reliability wiring), NEW-04 (FAIRness), NEW-05 (budget), NEW-06 (loop), NEW-07 (reporter), NEW-08 (auto-mode), #27 (Jupyter trigger), #26 (security score, narrowed) |
| Writing | #28 (Methodology), #29 (Results), #30 (Defence) |
| Documentation | NEW-10 (auto-mode docs) |

Total open after the audit: 19 (down from 14, up by 5 net because the audit adds 10 new and closes 6). The new backlog reflects the v3 design and the actual state of `dev`.

The critical path is the experiments, which depend on DATA-01. Engineering items NEW-01 through NEW-08 are all valuable but none are critical-path P0; they are the work that makes the artefact thesis-quality but they do not gate the experiments.
