# Issue tracking reconciliation, May 2026

Purpose: bring the GitHub backlog of `assaban/qallm-uva` into agreement with what is actually on `dev`. This file is the action list; run it with the `gh` CLI or the web UI. It builds on `docs/backlog-audit-2026-05.md` and corrects it where work has shipped since that audit.

Status legend: **CLOSE** (work done or superseded), **EDIT** (still valid, body stale), **KEEP** (valid, no change), **CREATE** (new tracking issue), **DISCUSS** (needs a supervisor decision).

Verification basis: every "implemented" claim below was checked against the `dev` tree on 29 May 2026. Module paths are given so each close is auditable.

---

## 1. Close (work shipped or superseded)

These are open issues whose work is complete on `dev` or duplicated by a newer issue. Close each with the comment shown.

| # | Title | Why close | Evidence on dev |
| --- | --- | --- | --- |
| 7 | RESEARCH-01: Baseline (Hypothesis) | Done + dup of #19 | `src/qallm/verification/hypothesis_baseline.py` (PR #31) |
| 10 | RESEARCH-02: False Confidence Rate | Dup of #24 | superseded |
| 11 | FEAT-08: Jupyter Frontend Trigger | Dup of #27 | superseded |
| 19 | FEAT-07: Hypothesis Baseline Generator | Done | `hypothesis_baseline.py`; `--strategy hypothesis` works |
| 20 | FEAT-08: Strategy Router in Orchestrator | Done | `orchestrator.py` routes `feedback\|oneshot\|hypothesis` |
| 21 | RESEARCH-01: Pilot Three-Strategy Comparison | Done (expanded scope) | pilot over 31 functions, 3 models, p < 0.005 |

Suggested close comments:

- **#7** → "Implemented in PR #31 (`src/qallm/verification/hypothesis_baseline.py`). Superseded in the newer backlog by #19. Closing."
- **#10** → "Superseded by #24, which has the full methodology and acceptance criteria. Closing as duplicate."
- **#11** → "Superseded by #27 (same scope, full acceptance criteria). Closing as duplicate."
- **#19** → "Implemented and merged (PR #31). `--strategy hypothesis` available in CLI and orchestrator; pilot across 31 functions confirms comparable JSON output. Closing."
- **#20** → "All acceptance criteria met. Strategy routing is live in `qallm.orchestrator`; the canonical verifier is now named `feedback` with `rl` kept as a back-compat alias. Closing."
- **#21** → "Completed with expanded scope: 31 functions across 5 files, three models, all pairwise Wilcoxon p < 0.005, 91.3% false-confidence rate. This is the pilot cited in the midterm presentation. Closing."

---

## 2. Edit (still valid, body out of date)

| # | Title | Edit |
| --- | --- | --- |
| 22 | DATA-01: Acquire Li's Dataset | KEEP open; note the request to Nafis has been sent. Remove `blocked` only when the dataset arrives. |
| 24 | RESEARCH-03: False Confidence Rate (RQ2) | KEEP open; add: "Pilot-scale FCR computed (91.3% over 31 functions). Full 200-notebook scale awaits DATA-01." |
| 26 | FEAT-09: Verification-Based Quality Metrics | See below: now fully addressed; recommend CLOSE. |

### #26 is now closeable

The audit left #26 partly open because the "Security Assessment Score with CWE coverage" piece was unbuilt. It is now built. The four metrics:

- Functional Correctness Score → produced as `test_pass_rate` (Reliability indicator, `qallm.evaluation`).
- Verification Coverage → produced as coverage delta in the verification session.
- False Confidence Rate → computed in the pilot.
- Security Assessment Score with CWE coverage → **now implemented** as the `bandit.cwe_classes` evaluator, wired into the Security dimension of `IMPLEMENTATION_DEFAULT`.

Suggested action: **CLOSE #26** with: "All four metrics are now produced by the pipeline. The final piece, CWE-class coverage on the Security dimension, shipped as the `bandit.cwe_classes` evaluator in `qallm.evaluation` / `qallm.profiles`. Closing."

---

## 3. Keep open (valid, no change)

| # | Title | Note |
| --- | --- | --- |
| 23 | RESEARCH-02: Full RQ1 Experiment (200 notebooks) | Depends on DATA-01. Add forward-ref to workflow-design.md section 9.5 if desired. |
| 27 | FEAT-10: Jupyter Frontend Trigger | Not yet built; aligns with RQ3. Sole tracking issue after #11 closes. |
| 28 | THESIS-01: Methodology chapter | Primary source: `docs/workflow-design.md`. |
| 29 | THESIS-02: Results chapter | Depends on RESEARCH-02, -03, -04. |
| 30 | THESIS-03: Defence preparation | Final deck. |

---

## 4. Discuss with supervisors

| # | Title | Question |
| --- | --- | --- |
| 25 | RESEARCH-04: Expert Validation Study (RQ2+RQ3) | Is the user study in scope for a single-author MSc, or future work? If no study runs, RQ3 ("actionable feedback to researchers") may need softening. Raise with Nafis. |

---

## 5. Work shipped without a tracking issue (NEW-01..NEW-10)

The audit proposed these as issues to create from workflow-design.md section 12. **Most are already implemented on `dev`.** Do not create them as open work; if you want a record, create them and immediately close them referencing the module, or simply note here that the code is the record.

| Item | Description | Status on dev | Evidence |
| --- | --- | --- | --- |
| NEW-01 | Test suite persistence | DONE | `src/qallm/verification/test_persistence.py` |
| NEW-02 | Judge module (3 strategies) | DONE | `src/qallm/judge/` |
| NEW-03 | Reliability wired to verification | DONE | `qallm.verification.pass_rate` in `evaluation.py` |
| NEW-04 | FAIRness indicators | DONE | `src/qallm/fairness.py` |
| NEW-05 | Budget + cost estimation | DONE | budget/cost in `orchestrator.py` |
| NEW-06 | Extended orchestrator loop | DONE | `orchestrator.run()` |
| NEW-07 | Reporter: lineage, abandoned log, JSON | DONE | lineage/abandon in reporter + orchestrator |
| NEW-08 | Auto-mode drives the real loop | DONE | fixed in PR #64 + this session's UI convergence |
| NEW-09 | HumanEval validation experiment | DONE | `src/qallm/experiments/humaneval_*` |
| NEW-10 | useAutoRunner walkthrough (knowledge debt) | N/A | resolved by the convergence rewrite + docstrings |

Recommendation (matches the audit): do **not** create retrospective open issues for these. The merged PRs and this document are the record. Mention this file in the next supervisor update so there is a single place listing what shipped.

---

## 6. This session's changes (for the PR description / next update)

Branch `refactor/debt-favicon-cwe-docs`, four commits:

1. `refactor(analysis)`: removed the deprecated `LifecycleNormalizer` (dead code).
2. `fix(web)`: serve a favicon; eliminates the `/favicon.ico` 404 (known open issue).
3. `feat(evaluation)`: `bandit.cwe_classes` CWE-coverage metric on the Security dimension (closes the last piece of #26).
4. `docs`: one-source-of-truth pass; README defers to `workflow-design.md` and `deployment.md`, plus a documentation-map index.

Tests: 365 passed (was 363; +3 favicon/CWE tests, −3 for the removed normaliser test, +2 favicon). Frontend type-checks and builds.

---

## How to execute (gh CLI)

```bash
# Closes
for n in 7 10 11 19 20 21 26; do
  gh issue close "$n" --repo assaban/qallm-uva --comment "See reconciliation doc section for rationale."
done
# Edit labels (example: unblock DATA-01 once the dataset arrives)
# gh issue edit 22 --repo assaban/qallm-uva --remove-label blocked
```

Replace the generic comment with the per-issue comments in section 1. Review each close before running; the loop above is a convenience, not a substitute for reading.
