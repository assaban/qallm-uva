# QALLM documentation

The documentation is grouped by purpose. Start with the top-level
[`README`](../README.md) for the project overview; this index is the map to the
deeper material.

## concepts/ — the ideas behind QALLM

The reasoning the thesis rests on.

- [`concepts/surpassing-static-analysers.md`](concepts/surpassing-static-analysers.md): the static-versus-execution argument (the verification gap, confirm/refute, verified fixes).
- [`concepts/oracles.md`](concepts/oracles.md): the verification oracles (crash, property, metamorphic).
- [`concepts/oracles-and-defect-classes.md`](concepts/oracles-and-defect-classes.md): which oracle catches which defect class, and why the correctness oracle withholds the implementation (illustrated).
- [`concepts/oracle-confidence-mutation-testing.md`](concepts/oracle-confidence-mutation-testing.md): mutation-testing the oracle to give every gap finding a confidence (the positive soundness check; illustrated).

## guides/
- [`guides/getting-started.md`](guides/getting-started.md): first-time user guide (what the tool does, your first run, manual vs automatic, reading results). — how to run and operate QALLM

Practical, task-oriented.

- [`guides/running-experiments.md`](guides/running-experiments.md): venv setup and running the experiments directly.
- [`guides/deployment.md`](guides/deployment.md): production deployment (split frontend/API, CORS, TLS, operations).
- [`guides/sonarqube-integration.md`](guides/sonarqube-integration.md): SonarQube setup and integration.
- [`guides/jupyter-magic.md`](guides/jupyter-magic.md): the `%%qallm` Jupyter magic.
- [`guides/documentation-style-guide.md`](guides/documentation-style-guide.md): how we write QALLM docs (categories, shape, status markers, diagrams, vocabulary).

## architecture/ — how QALLM works inside

The mechanics and design record.

- [`architecture/workflow-design.md`](architecture/workflow-design.md): what QALLM does (the loop, judge, budget, quality frameworks).
- [`architecture/run-mechanics-and-diagnostics.md`](architecture/run-mechanics-and-diagnostics.md): rounds, FROZEN+GROW test accumulation, ERROR vs BUG.
- [`architecture/verification-repair-reward-design.md`](architecture/verification-repair-reward-design.md): the verification/repair/reward design and the key observations behind it.
- [`architecture/web-ui-automode.md`](architecture/web-ui-automode.md): auto-mode web UI behaviour.
- [`architecture/web-ui-history.md`](architecture/web-ui-history.md): the Experiments and Sessions history views.
- [`architecture/design/`](architecture/design/): per-feature design specifications (FEAT-01 .. FEAT-05).

## experiments/ — the evaluation

- [`experiments/protocol.md`](experiments/protocol.md): the reproducible experiment protocol for both tracks (the source of truth for Chapter 5).
- [`experiments/run-outline.md`](experiments/run-outline.md): the ordered set of runs to execute, with exact commands and what each produces.
- [`experiments/humaneval.md`](experiments/humaneval.md): the HumanEvalFix validation harness in detail.
- [`experiments/reliability-oracle-findings.md`](experiments/reliability-oracle-findings.md): why reliability bugs were missed (oracle-type mismatch, implementation anchoring), from the lab artifacts.
- [`experiments/oracle-variance-and-consensus.md`](experiments/oracle-variance-and-consensus.md): single-shot oracle variance across runs, the oracle-threading correction, and the consensus design.
- [`experiments/lab-calibration-result.md`](experiments/lab-calibration-result.md): the decisive lab result (5/5 reliability recall, 0 false positives under consensus + voting).

## thesis/ — thesis-facing material

- [`thesis/thesis-draft-scaffold.md`](thesis/thesis-draft-scaffold.md): the thesis structure and metric definitions.
- [`thesis/methodology-decisions.md`](thesis/methodology-decisions.md): the dated, append-only record of methodology decisions (MD-001, MD-002, ...).
- [`thesis/roadmap.md`](thesis/roadmap.md): priorities and rationale.
- [`thesis/status-update-2026-06.md`](thesis/status-update-2026-06.md): supervisor-facing status summary (the story, architecture, judge/EVERSE, calibration evidence) with diagrams.
- [`thesis/experiment-plan.md`](thesis/experiment-plan.md): the experiments that answer each RQ, with exact commands and outputs.
- [`thesis/experiment-catalog.md`](thesis/experiment-catalog.md): additional experiments beyond the core set (.py vs .ipynb, oracle ablation, rounds sensitivity, sampling pilot, cross-model), with commands and scope.
- [`thesis/thesis-structure-and-plan.md`](thesis/thesis-structure-and-plan.md): chapter structure, the three-contribution framing, per-section checklist, and writing-status tracker.
- [`thesis/audit-2026-06.md`](thesis/audit-2026-06.md): full project audit (strengths, prioritised risks, web-UI assessment, punch list).
- [`thesis/rq-evolution.md`](thesis/rq-evolution.md): how the research questions changed from the proposal and why (defence-ready motivation).
- [`thesis/llm-training-analysis.md`](thesis/llm-training-analysis.md): what training an LLM would take, its value, a staged plan, and why it is future work.
- [`thesis/path-to-finish-2026-06.md`](thesis/path-to-finish-2026-06.md): status as E1 runs, the partial-data findings, and the ordered path to delivery.
- [`thesis/status-checkpoint-2026-06-16.md`](thesis/status-checkpoint-2026-06-16.md): point-in-time checkpoint (done / in flight / remaining / risks).
- [`thesis/enrichment-ideas.md`](thesis/enrichment-ideas.md): candidate features and experiments to enrich QALLM, with value/effort/risk and a thesis-scope vs future-work split.
- [`thesis/security-confirmation-scope.md`](thesis/security-confirmation-scope.md): scope/feasibility/risk-benefit analysis for making security findings confirm rather than land inconclusive (decision aid).
- [`thesis/session-log.md`](thesis/session-log.md): append-only, dated record of what changed each session and what is outstanding (for cross-session continuity).

## showcase/ — shareable, self-contained pages

- [`showcase/verification-gap-explainer.html`](showcase/verification-gap-explainer.html): the interactive verification-gap explainer (also an in-app tab).
- [`showcase/qallm-overview.html`](showcase/qallm-overview.html): a one-page overview.

## Datasets

Lab and validation corpora live outside `docs/`, under [`datasets/`](../datasets/):
the committed lab set ([`datasets/lab/MANIFEST.md`](../datasets/lab/MANIFEST.md))
and the ENVRI fetcher (`scripts/fetch_envri_dataset.py`).

- [`docs/architecture/sessions-vs-experiments.md`](architecture/sessions-vs-experiments.md): how interactive web sessions are kept separate from batch experiment runs.

- [`docs/thesis/e1-results-analysis.md`](thesis/e1-results-analysis.md): first-pass analysis of the E1 headline run, with the counts and the gap-rate caveat.

- [`docs/thesis/doc-consolidation-plan.md`](thesis/doc-consolidation-plan.md): proposal to consolidate the docs (for sign-off).
