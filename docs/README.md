# QALLM documentation

The documentation is grouped by purpose. Start with the top-level
[`README`](../README.md) for the project overview; this index is the map to the
deeper material.

## concepts/ — the ideas behind QALLM

The reasoning the thesis rests on.

- [`concepts/surpassing-static-analysers.md`](concepts/surpassing-static-analysers.md): the static-versus-execution argument (the verification gap, confirm/refute, verified fixes).
- [`concepts/oracles.md`](concepts/oracles.md): the verification oracles (crash, property, metamorphic).
- [`concepts/oracles-and-defect-classes.md`](concepts/oracles-and-defect-classes.md): which oracle catches which defect class, and why the correctness oracle withholds the implementation (illustrated).

## guides/ — how to run and operate QALLM

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
- [`architecture/web-ui-automode.md`](architecture/web-ui-automode.md): auto-mode web UI behaviour.
- [`architecture/web-ui-history.md`](architecture/web-ui-history.md): the Experiments and Sessions history views.
- [`architecture/design/`](architecture/design/): per-feature design specifications (FEAT-01 .. FEAT-05).

## experiments/ — the evaluation

- [`experiments/protocol.md`](experiments/protocol.md): the reproducible experiment protocol for both tracks (the source of truth for Chapter 5).
- [`experiments/run-outline.md`](experiments/run-outline.md): the ordered set of runs to execute, with exact commands and what each produces.
- [`experiments/humaneval.md`](experiments/humaneval.md): the HumanEvalFix validation harness in detail.
- [`experiments/reliability-oracle-findings.md`](experiments/reliability-oracle-findings.md): why reliability bugs were missed (oracle-type mismatch, implementation anchoring), from the lab artifacts.
- [`experiments/oracle-variance-and-consensus.md`](experiments/oracle-variance-and-consensus.md): single-shot oracle variance across runs, the oracle-threading correction, and the consensus design.

## thesis/ — thesis-facing material

- [`thesis/thesis-draft-scaffold.md`](thesis/thesis-draft-scaffold.md): the thesis structure and metric definitions.
- [`thesis/methodology-decisions.md`](thesis/methodology-decisions.md): the dated, append-only record of methodology decisions (MD-001, MD-002, ...).
- [`thesis/roadmap.md`](thesis/roadmap.md): priorities and rationale.
- [`thesis/session-log.md`](thesis/session-log.md): append-only, dated record of what changed each session and what is outstanding (for cross-session continuity).

## showcase/ — shareable, self-contained pages

- [`showcase/verification-gap-explainer.html`](showcase/verification-gap-explainer.html): the interactive verification-gap explainer (also an in-app tab).
- [`showcase/qallm-overview.html`](showcase/qallm-overview.html): a one-page overview.

## Datasets

Lab and validation corpora live outside `docs/`, under [`datasets/`](../datasets/):
the committed lab set ([`datasets/lab/MANIFEST.md`](../datasets/lab/MANIFEST.md))
and the ENVRI fetcher (`scripts/fetch_envri_dataset.py`).
