# QALLM roadmap

A grounded plan for what makes QALLM great, ordered by leverage. This is not a
wish list; every item below is justified by the current state of the code, the
audit findings, or a concrete thesis need. 

## Where QALLM is today

The pipeline is complete and the architecture is sound. The verification-gap
track runs end to end (all three metrics from one command), and the calibration
instrument now works: on the lab set the correctness oracle catches 5/5 seeded
reliability bugs. Getting there surfaced and fixed a chain of issues, the gap
was being measured at the wrong round, the oracle type was mismatched to
reliability defects, the implementation body was anchoring the test generator,
the oracle was not actually reaching round-0 generation, and consensus was
silently disabled by an empty-session guard. Each is now fixed and documented
(see docs/experiments/lab-calibration-result.md and oracle-variance-and-consensus.md).
The codebase remains clean: ruff clean, 650+ passing tests. The remaining work
is the headline experiment and the write-up, not detector correctness.

## Tier 1: thesis-critical (do before the full experiment run)

These directly determine whether the thesis results are trustworthy and
defensible. Highest leverage.

0. **Confirm the lab calibration with consensus actually running.** The
   empty-session guard that disabled consensus is fixed; re-run
   `--oracle correctness --samples 5` and confirm clean_control 0,
   complexity_findings 0, reliability_gap 5. This is the gate that says the
   instrument is sound. Cheap, decisive, do it first.

1. **Run the full verification-gap experiment (ENVRI) and fill Chapter 5.** The
   machinery exists (`scripts/run_gap_experiment.py --confirm`). Run with
   `--oracle correctness --samples 5` under tmux, metrics_only retention, and
   report the gap rate with its 95% CI. This converts the bracketed
   placeholders in the thesis scaffold into real numbers. Everything else is
   secondary to this.

2. **Harden the statistical layer (started).** `stats.py` is now tested and a
   JSON-serialisation bug is fixed. Remaining: add a confidence interval or
   bootstrap to the gap rate so the headline figures carry uncertainty,
   examiners expect an interval, not a point estimate. Small, high-credibility.

3. **Surface generated-test quality as a reported number.** Incoherent-oracle
   tests are currently dropped to a log. Surface a per-session
   `incoherent_oracles_dropped` count in `summary.json` (like `units_skipped`),
   so the thesis can state generated-test quality as data, and so the
   threats-to-validity argument (MD-002) is backed by a measured figure.

4. **Determinism and provenance manifest. DONE.** Every run now emits a
   `manifest.json` whose `provenance` block captures commit hash, branch,
   dirty-tree flag, package version, Python/platform, and a dataset fingerprint
   (file count + hash over sorted paths), via `experiments/provenance.py`.
   Capture is best-effort (never blocks a run). Any number now traces back to
   exact conditions.

**Tier 1 is complete.** The instrument is calibrated (5/5 reliability recall),
the headline machinery runs with confidence intervals and mutation-based
per-finding confidence, generated-test quality is reported, RQ2/RQ3 are
unblocked (round_00 fix), and every run is provenance-stamped. The remaining
Tier-1 item, the ENVRI headline run itself, is an execution step, not code.

## Tier 2: coverage and robustness (de-risks the artifact)

The audit found the static-analysis adapters at 0% direct coverage. They
produce the findings the entire gap metric depends on, so they are the most
load-bearing untested code.

5. **Test the analyzer adapters. SUBSTANTIALLY DONE.** The normalised finding
   shape is now pinned: `radon_normalizer` 100% (CC/MI thresholds and severity
   bands), `trufflehog` mapper 93% (JSONL secret -> issue shape, multi-line,
   blank-line and missing-metadata handling), `bandit._safe_parse` fully covered
   (ANSI strip + JSON recovery from noisy output), `util.get_snippet` 89%.
   Analysis-package coverage is 87%. If a tool's output format shifts, these
   tests now catch the change instead of the gap metric drifting silently. The
   remaining uncovered lines are subprocess-invocation paths (need the tool
   binary installed), exercised by the dynamic integration tests.

6. **Audit the broad excepts.** 33 `except Exception` sites; most are
   defensible isolation (one bad notebook should not sink a batch), but a few
   may swallow signal. Triage: keep the isolation ones, narrow or log the rest.
   Low glamour, real robustness for the dataset run.

7. **Repair-manager and generator coverage.** `repair_manager.py` (33%) and
   `generator.py` (36%) are core pipeline; raise to parity with the rest.

## Tier 3: the demo and knowledge-sharing surface (impact and dissemination)

The verification-gap explainer (standalone + in-app "The Gap" tab) is the
first of a family. These make QALLM legible to supervisors, committees, and a
conference audience, directly serving the publication and impact goals.

8. **In-app Architecture page.** An interactive four-stage pipeline view
   (ingest, analyse, execute and confirm, verify) reusing the AboutView
   patterns. Turns "how does it work" into a click-through.

9. **Live metrics page.** Pull `/api/metrics/aggregate` so the app shows its
   own real numbers once the dataset run is done. The thesis result, live in
   the tool.

10. **Conference one-pager and short demo script.** A reproducible 3-minute
    walkthrough (upload, watch the gap appear, see the fix proven) plus a
    polished one-pager. Cheap, high dissemination value.

## Tier 4: research extensions (the PhD arc)

Beyond the thesis, these are where QALLM becomes a multi-year contribution.

11. **Per-round verified-fix tracking.** Currently confirm/verify run against
    baseline and final source. Tracking fix verification per round would show
    the repair trajectory, not just the endpoint, richer evidence for the RL
    outperformance claim.

12. **Security-relevant defect classes.** The thesis positions QALLM to extend
    into security; the eval/shell/pickle examples already exercise this. A
    focused study on security findings (confirmation rates for injection,
    deserialisation, secret-exposure) is a natural paper and the PhD bridge.

13. **Multi-model comparison study.** The provider abstraction supports it
    (OpenAI, Anthropic, FedLLM, Ollama). A systematic comparison of
    verification-gap and repair rates across models is publishable and
    strengthens external validity.

14. **Oracle-quality as a first-class research question.** The incoherent
    oracle filter (MD-002) hints at a deeper question: how often do LLM-
    generated tests assert correct properties at all? Measuring and improving
    generated-oracle validity is a contribution in its own right.

## What NOT to do (avoiding churn)

- Do not over-refactor the architecture; it is sound and the audit found no
  structural debt. Resist large rewrites that risk the passing suite.
- Do not move test tooling out of `dependencies` mid-thesis unless CI forces
  it; the recurring undeclared-dep issues are resolved case by case and a
  restructure now is risk without reward.
- Do not chase 100% coverage. 75% with the load-bearing paths (metrics, gap,
  stats, validators) covered is the right target for a research artifact;
  spend coverage effort only where a silent change would corrupt a result.

## Suggested order

Tier 1 fully, then 5 and 6 from Tier 2 (the load-bearing coverage), then the
Tier 3 demo surface in parallel with thesis writing. Tier 4 is the PhD
proposal material, sketch it in the thesis future-work chapter, build it after.
