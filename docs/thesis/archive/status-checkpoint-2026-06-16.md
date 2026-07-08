> **Superseded.** Historical snapshot; the live status is `../STATUS.md`, the plan is `../roadmap.md`.

# QALLM status checkpoint, June 16 2026

A point-in-time snapshot to anchor where the project stands, what is done, what
is in flight, and what remains. Use this as the reference when picking the work
back up.

## One-paragraph summary

QALLM is feature-complete and deployed. The pipeline runs end to end (static
baseline, execution-based verification, repair, EVERSE-aligned judge, report),
the instrument is calibrated on the lab set, the three contributions
(verification-gap method, EVERSE judge, mutation-based oracle confidence) are all
implemented and surfaced in the UI, and the tool is live on the VM and being
used by external testers. The headline experiment (E1, the ENVRI verification
gap) is running. The thesis draft covers every results-independent section. What
remains is finishing E1, the RQ2/RQ3 confirm pass, and writing the results
chapters.

## What is done

- **Pipeline**: ingestion (.py and .ipynb), five static analysers via a
  registry, sandboxed execution, repair loop, lexicographic EVERSE judge,
  resumable parallel runner, provenance manifests.
- **Three contributions, all implemented and tested**: the verification gap
  (RQ1), confirm/refute with legible inconclusive/not-testable accounting (RQ2),
  verified fixes (RQ3), and mutation-based oracle confidence, now correctly
  scored against the repaired (correct) source rather than the buggy original.
- **Calibration**: lab set validated, reliability 5/5, clean controls clean,
  RQ2 legible, confidence no longer collapsing to "unknown".
- **Web UI**: full pipeline UI (manual and auto modes), the gap panel with the
  confidence view, expandable finding detail, a re-analyse comparison that now
  shows which findings were resolved / introduced / still present, an end-user
  onboarding intro and clarified mode descriptions, a curated Docs tab opening
  on a user getting-started guide (with a pipeline diagram).
- **Deployment**: live on nis05.lab.uvalight.net via docker compose; first
  external tester feedback received and acted on.
- **Quality**: 729 passing tests, ruff clean, frontend builds clean.
- **Thesis draft**: Introduction, Background (2.1 to 2.5), Method (3.1 to 3.9),
  Implementation (4.1 to 4.6), Setup (5.1), Threats (5.5), Appendix definitions,
  plus the planning docs (experiment plan, structure, RQ evolution, LLM-training
  analysis, enrichment ideas, experiment catalog, security-confirmation scope).

## In flight

- **E1, the ENVRI verification-gap headline run.** Partial data already shows
  the gap materialising (hundreds of execution-only defects across the corpus).
  Confidence labels from before the repaired-source fix should be re-scored once
  the run completes; the gap counts are unaffected.
- **SonarQube on the VM**: server is up and the scanner is installed on the
  host, but the containerised api needs `SONARQUBE_TOKEN` in `.env` and
  `WITH_SONAR_SCANNER=1` (rebuild) for it to register. Optional; not on the
  critical path. Documented in `.env.example`.

## What remains (the critical path)

1. Finish E1; re-score its confidence over the artefacts.
2. Run E2/E3 (the `--confirm` pass on ENVRI) for RQ2/RQ3.
3. Draft results 5.2 to 5.4 with the confidence-stratified (A1) and
   per-EVERSE-dimension (A2) cuts.
4. Draft Discussion, Conclusion, and Abstract, making the thesis
   content-complete.
5. Editing pass into the LaTeX template.

## Off the critical path (future work / optional)

Training an LLM (future work / PhD), safe security confirmation, broader oracle
types, cross-model comparison, the .py-vs-.ipynb and oracle ablation
experiments. All named in the experiment catalog and enrichment-ideas docs.

## Health indicators

- Tests: 729 passing.
- Lint: clean.
- Frontend: builds clean; deployed.
- Calibration: instrument sound on the lab answer key.
- External use: live, with tester feedback incorporated.

## Risks to watch

- E1 runtime (large corpus; sampling is available for a faster representative
  signal if needed).
- A small fraction of notebooks error and are isolated (logged with tracebacks
  now); worth a glance once E1 finishes to confirm the loss rate is acceptable.
- The thesis results chapters are the main remaining writing effort and depend
  on E1/E2/E3 completing.

## One-line status

Feature-complete, calibrated, deployed, and in use; headline experiment running;
remaining work is finish the runs and write the results.
