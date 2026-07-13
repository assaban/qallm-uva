# QALLM documentation

The documentation is grouped by purpose. Start with the top-level
[`README`](../README.md) for the project overview; this index is the map to the
deeper material.

## Authority and naming

If two sources disagree, precedence is: **code > methodology log > everything
else**. The code is what actually runs; `thesis/methodology-decisions.md` is
the append-only record of why it runs that way; all other docs describe and
must yield to those two.

Naming convention:

- **guides/**: imperative how-to titles (`running-experiments`, `deployment`).
- **concepts/**: the idea named directly (`oracles`, `surpassing-static-analysers`).
- **architecture/**: the subsystem named (`workflow-design`, `run-mechanics-and-diagnostics`).
- **thesis/**: durable nouns (`experiment-plan`, `roadmap`, `STATUS`); no dates
  in living-doc names. Dated snapshots belong in `thesis/archive/` only.
- **experiments/**: protocols use durable names (`protocol`); point-in-time
  findings carry their date (`lab-calibration-2026-06-19`), like design records.
- One append-only decision log: `thesis/methodology-decisions.md`. The
  `thesis/session-log.md` is a working diary, not an authority.

See [`guides/documentation-style-guide.md`](guides/documentation-style-guide.md)
for the full writing conventions.

## concepts/: the ideas behind QALLM

The reasoning the thesis rests on.

- [`concepts/surpassing-static-analysers.md`](concepts/surpassing-static-analysers.md): the static-versus-execution argument (the verification gap, confirm/refute, verified fixes).
- [`concepts/oracles.md`](concepts/oracles.md): the verification oracles and the defect classes each targets (merged reference; illustrated).
- [`concepts/oracle-confidence-mutation-testing.md`](concepts/oracle-confidence-mutation-testing.md): mutation-testing the oracle to give every gap finding a confidence (the positive soundness check; illustrated).

## guides/: how to run and operate QALLM

Practical, task-oriented.

- [`guides/getting-started.md`](guides/getting-started.md): first-time user guide (what the tool does, your first run, manual vs automatic, reading results).
- [`guides/running-experiments.md`](guides/running-experiments.md): venv setup for running the experiments directly (environment only; the steps themselves live in `experiments/HOW-TO-RUN-EXPERIMENTS.md`).
- [`guides/deployment.md`](guides/deployment.md): production deployment (split frontend/API, CORS, TLS, operations).
- [`guides/sonarqube-integration.md`](guides/sonarqube-integration.md): SonarQube setup and integration.
- [`guides/jupyter-magic.md`](guides/jupyter-magic.md): the `%%qallm` Jupyter magic.
- [`guides/documentation-style-guide.md`](guides/documentation-style-guide.md): how we write QALLM docs (categories, shape, status markers, diagrams, vocabulary).

## architecture/: how QALLM works inside

The mechanics and design record.

- [`architecture/workflow-design.md`](architecture/workflow-design.md): what QALLM does (the loop, judge, budget, quality frameworks).
- [`architecture/run-mechanics-and-diagnostics.md`](architecture/run-mechanics-and-diagnostics.md): rounds, FROZEN+GROW test accumulation, ERROR vs BUG.
- [`architecture/verification-repair-reward-design.md`](architecture/verification-repair-reward-design.md): the verification/repair/reward design and the key observations behind it.
- [`architecture/sessions-vs-experiments.md`](architecture/sessions-vs-experiments.md): how interactive web sessions are kept separate from batch experiment runs.
- [`architecture/web-ui-automode.md`](architecture/web-ui-automode.md): auto-mode web UI behaviour.
- [`architecture/web-ui-history.md`](architecture/web-ui-history.md): the Experiments and Sessions history views.
- [`architecture/design/`](architecture/design/): per-feature design specifications (FEAT-01 .. FEAT-05).

## experiments/: the evaluation

Scope rule for the three run-related docs: `experiments/protocol.md` owns the
definitions (metrics, formulas, environment, threats);
`thesis/experiment-plan.md` owns which runs answer which RQ;
`experiments/HOW-TO-RUN-EXPERIMENTS.md` owns the copy-paste operator steps.
Each defers to the others outside its scope.

- [`experiments/protocol.md`](experiments/protocol.md): the reproducible experiment protocol for both tracks (the source of truth for Chapter 5 definitions and procedure).
- [`experiments/HOW-TO-RUN-EXPERIMENTS.md`](experiments/HOW-TO-RUN-EXPERIMENTS.md): the operator playbook, copy-paste commands for each step from smoke test to full runs.
- [`experiments/playbook-targeted-experiments.md`](experiments/playbook-targeted-experiments.md): the seeded-comparison playbook (oracle ablation, cross-domain, form comparison).
- [`experiments/humaneval.md`](experiments/humaneval.md): the HumanEvalFix validation harness in detail.
- [`experiments/reliability-oracle-findings.md`](experiments/reliability-oracle-findings.md): why reliability bugs were missed (oracle-type mismatch, implementation anchoring), from the lab artifacts.

Point-in-time findings (dated records; superseded content carries a banner):

- [`experiments/oracle-variance-and-consensus.md`](experiments/oracle-variance-and-consensus.md): superseded by the single-sample setting; kept for the durable insight on why consensus-by-union fails.
- [`experiments/lab-calibration-result.md`](experiments/lab-calibration-result.md): the lab calibration summary (note: its `--samples 5` recommendation is superseded; single-sample is the live setting).
- [`experiments/lab-calibration-2026-06-18.md`](experiments/lab-calibration-2026-06-18.md) and [`experiments/lab-calibration-2026-06-19.md`](experiments/lab-calibration-2026-06-19.md): dated calibration run records.
- [`experiments/cross-evaluation-2026-06-18.md`](experiments/cross-evaluation-2026-06-18.md): cross-evaluation run record.
- [`experiments/mutation-confidence-fix-2026-06-18.md`](experiments/mutation-confidence-fix-2026-06-18.md): mutation-confidence fix record.
- [`experiments/rq2-reliability-confirmation-2026-06-20.md`](experiments/rq2-reliability-confirmation-2026-06-20.md): RQ2 reliability confirmation record.
- [`experiments/heval-correctness-final-2026-07-11.md`](experiments/heval-correctness-final-2026-07-11.md): the completed HumanEvalFix correctness arm and the full oracle-ablation numbers (McNemar exact; MD-009).
- [`experiments/cross-domain-and-form-2026-07-13.md`](experiments/cross-domain-and-form-2026-07-13.md): the 2x2 generality runs (domain x form): the gap reproduces in the ocean domain at the headline level and persists in authored plain Python.
- [`experiments/test-accumulation-findings-2026-06-18.md`](experiments/test-accumulation-findings-2026-06-18.md): FROZEN+GROW test accumulation findings.

## thesis/: thesis-facing material

- [`thesis/thesis-draft-scaffold.md`](thesis/thesis-draft-scaffold.md): the thesis structure and metric definitions.
- [`thesis/methodology-decisions.md`](thesis/methodology-decisions.md): the dated, append-only record of methodology decisions (MD-001, MD-002, ...). Authoritative after the code itself.
- [`thesis/roadmap.md`](thesis/roadmap.md): priorities and rationale (the single forward-looking plan).
- [`thesis/STATUS.md`](thesis/STATUS.md): the single point-in-time status, overwritten in place; superseded dated snapshots are in [`thesis/archive/`](thesis/archive/).
- [`thesis/experiment-plan.md`](thesis/experiment-plan.md): the experiments that answer each RQ (authoritative for which thesis runs exist and why).
- [`thesis/experiment-catalog.md`](thesis/experiment-catalog.md): additional experiments beyond the core set (.py vs .ipynb, oracle ablation, rounds sensitivity, sampling pilot, cross-model), with commands and scope.
- [`thesis/e1-results-analysis.md`](thesis/e1-results-analysis.md): first-pass analysis of the E1 headline run, with the counts and the gap-rate caveat.
- [`thesis/e2-results-analysis.md`](thesis/e2-results-analysis.md): the E2 full-corpus results (RQ1 three-view gap rate, RQ2 counts, RQ3 fix rate, truncation vignette, provenance note); every number regenerates via `scripts/analyze_gap_results.py`.
- [`thesis/e2-numbers.tex`](thesis/e2-numbers.tex): every E2 figure as a LaTeX macro, for `\input` into the thesis.
- [`thesis/thesis-structure-and-plan.md`](thesis/thesis-structure-and-plan.md): chapter structure, the three-contribution framing, per-section checklist, and writing-status tracker.
- [`thesis/audit-2026-06.md`](thesis/audit-2026-06.md): full project audit (strengths, prioritised risks, web-UI assessment, punch list).
- [`thesis/rq-evolution.md`](thesis/rq-evolution.md): how the research questions changed from the proposal and why (defence-ready motivation).
- [`thesis/llm-training-analysis.md`](thesis/llm-training-analysis.md): what training an LLM would take, its value, a staged plan, and why it is future work.
- [`thesis/enrichment-ideas.md`](thesis/enrichment-ideas.md): candidate features and experiments to enrich QALLM, with value/effort/risk and a thesis-scope vs future-work split.
- [`thesis/security-confirmation-scope.md`](thesis/security-confirmation-scope.md): scope/feasibility/risk-benefit analysis for making security findings confirm rather than land inconclusive (decision aid).
- [`thesis/doc-consolidation-plan.md`](thesis/doc-consolidation-plan.md): the executed documentation consolidation plan (kept as the record of what changed and why).
- [`thesis/session-log.md`](thesis/session-log.md): append-only working diary of what changed each session. Non-authoritative; if it disagrees with the code or the methodology log, they win.

## showcase/: shareable, self-contained pages

- [`showcase/verification-gap-explainer.html`](showcase/verification-gap-explainer.html): the interactive verification-gap explainer (also an in-app tab).
- [`showcase/qallm-overview.html`](showcase/qallm-overview.html): a one-page overview.

## Datasets

Lab and validation corpora live outside `docs/`, under [`datasets/`](../datasets/):
the committed lab set ([`datasets/lab/MANIFEST.md`](../datasets/lab/MANIFEST.md))
and the ENVRI fetcher (`scripts/fetch_envri_dataset.py`).
