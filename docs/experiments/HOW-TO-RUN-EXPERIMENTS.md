# How to run the QALLM experiments

> **Scope.** The operator playbook: copy-paste steps in order. For why each run
> exists and which RQ it answers, see `../thesis/experiment-plan.md`
> (authoritative for the thesis runs; if commands disagree, the plan wins). For
> metric definitions and formulas, see `protocol.md`.

If you are unsure what to run, read THIS section only. Copy the block for the
step you are on, paste it, wait. The rest of the document explains why each step
exists; you do not need it to run them.

Before any run, once per shell:

    cd ~/qallm-uva
    source .venv/bin/activate
    export FEDLLM_API_KEY=...        # from Nafis

## The decision: which command do I run?

- Just want to prove the pipeline works? -> Step 0 (smoke).
- Validating the instrument against the answer key? -> Step 1 (lab).
- Want the RQ1 gap counts on real notebooks? -> Step 2 (E1).
- Want the real gap RATE plus RQ2 and RQ3? -> Step 3 (E2). This is the one the
  thesis headline needs. RQ1 alone gives a degenerate rate of 1.0.
- Strategy comparison / "RL beats baseline"? -> Step 4 (HumanEvalFix).
- Bigger corpus for breadth? -> Step 5 (Li dataset).

## Copy-paste commands

Step 0, smoke test (minutes):

    python scripts/run_gap_experiment.py \
        --dataset datasets/lab --output runs/smoke \
        --pattern "*.py" --llm fedllm --rounds 2

Step 1, lab calibration (the control, ~40 min):

    python scripts/run_gap_experiment.py \
        --dataset datasets/lab --output runs/lab_calibration \
        --pattern "*.py" --llm fedllm --rounds 5 --oracle correctness \
        --samples 1 --confirm --mutation-confidence

Step 2, E1 ENVRI headline RQ1 (free, hours):

    python scripts/run_gap_experiment.py \
        --dataset datasets/envri_forest --output runs/e1_rq1_headline \
        --pattern "*.ipynb" --llm fedllm --rounds 5 --oracle correctness \
        --samples 1 --workers 4 --mutation-confidence

Step 3, E2 ENVRI RQ2 + RQ3 + the real gap rate (free, hours). Same as E1 plus
--confirm. E3 is not a separate run; verified_fix_rate comes out of this one:

    python scripts/run_gap_experiment.py \
        --dataset datasets/envri_forest --output runs/e2_rq2 \
        --pattern "*.ipynb" --llm fedllm --rounds 5 --oracle correctness \
        --samples 1 --workers 4 --confirm --mutation-confidence

Step 4, E4 HumanEvalFix validation + strategy comparison:

    python scripts/run_humaneval.py \
        --output runs/humaneval --workers 4 --strategy feedback
        --oracle correctness
    # repeat with --strategy oneshot and --strategy hypothesis to compare

Step 5, Li corpus at scale (free, long; same as E2, bigger dataset):

    python scripts/run_gap_experiment.py \
        --dataset datasets/li_notebooks --output runs/e4_scale \
        --pattern "*.ipynb" --llm fedllm --rounds 5 --oracle correctness \
        --samples 1 --workers 4 --confirm --mutation-confidence

## Knobs you may add to any command

- Fast trial on a subset: --sample 150 --sample-seed 42 --sample-stratify
- Spend cap on a paid model: --max-cost-usd 5 (halts cleanly at the cap)
- Switch model: --llm openai --model gpt-4o-mini (or --llm anthropic)
- Keep full per-round artefacts (large): --retention full

## After a run, send these four files

From the output directory you chose (for example runs/e2_rq2):

    aggregate.json      the count-weighted rates plus the inputs block
    manifest.json       provenance: commit, model, environment, dataset hash
    metrics.csv         one row per session, easy to scan
    results.jsonl       per-session metrics

If unsure of names, run: `find <output_dir> -maxdepth 2 -type f` and send that.

## Reading the result in one glance (metrics.csv columns)

- verification_gap_rate: RQ1. Trustworthy only when confirm was on.
- confirmation_rate: RQ2. confirmed / (confirmed + refuted).
- verified_fix_rate: RQ3. verified_fixed / (verified_fixed + not_fixed).
- not_execution_testable: complexity/maintainability findings, excluded by design.
- inconclusive: could not be decided (for example security without an oracle).
- confidence on a gap finding: needs --mutation-confidence AND a working scorer.

---

The full set of runs to produce the thesis results, in order. Each step gives
the exact command, what it produces, and what to record. Run them from the repo
root on the VM with the venv active (`source .venv/bin/activate`). Dashes are
avoided as punctuation per the project convention.

Three research questions drive everything:

- RQ1, the verification gap: how often does execution find a runtime defect in
  code that static analysis passed? (verification_gap_rate)
- RQ2, confirmation: of the static findings, how many does execution confirm
  vs refute? (confirmation_rate)
- RQ3, repair: of confirmed defects, how many does the loop verifiably fix?
  (verified_fix_rate)

Two datasets serve two different purposes:

- The lab set (`datasets/lab`, 4 files, known answer key) is for CALIBRATION:
  because the expected findings are known, it yields precision/recall and a
  false-positive rate, characterising how QALLM errs.
- The ENVRI corpus (`datasets/envri_forest`, ~289 real notebooks) is for the
  HEADLINE numbers: the gap rate at scale on real research code.
- HumanEvalFix (downloaded at run time) is the VALIDATION benchmark with known
  planted bugs, for the strategy comparison (feedback vs oneshot vs hypothesis)
  and the "RL outperforms" claim.

Set the model once. FedLLM is the default and free for VO users:

    export FEDLLM_API_KEY=...        # from Nafis; rotate after the runs

Confirm egress before a long run:

    curl https://llm.ai.egi.eu/v1/models -H "Authorization: Bearer $FEDLLM_API_KEY"

---

## Step 0: smoke test (minutes, do this first)

Prove the whole chain works end to end on a tiny input before spending hours.

    python scripts/run_gap_experiment.py \
        --dataset datasets/lab --output runs/smoke \
        --pattern "*.py" --llm fedllm --rounds 2

Expect: `runs/smoke/aggregate.json` with a non-null verification_gap_rate, and
no per-unit lineage bloat (metrics_only is the default). If this fails, stop
and fix before scaling up. If it succeeds, the pipeline, model egress, and
output writing are all confirmed.

---

## Step 1: lab calibration (the control, run before the headline)

This is the step that makes the headline trustworthy. Because the lab set has a
verified answer key (`datasets/lab/MANIFEST.md`), you can report not just a gap
rate but how QALLM performs against ground truth: does it find the seeded
reliability bugs, does it stay silent on the clean control, does it correctly
treat complexity findings as not execution testable.

    python scripts/run_gap_experiment.py \
        --dataset datasets/lab --output runs/lab_calibration \
        --pattern "*.py" --llm fedllm --rounds 5 --confirm

Note: `--confirm` forces full artefact retention (it needs per-round artefacts
on disk for RQ2/RQ3); that is expected and fine for a 4-file set.

What to record (the calibration result, against MANIFEST.md):

- reliability_gap.py: all 5 seeded runtime bugs should appear as execution-only
  defects. Count true positives / 5.
- security_findings.py: the eval and shell findings should be confirmed; the
  SQL one has no DB oracle, so it should land as not-confirmable. Check the
  confirmation outcomes match.
- complexity_findings.py: should classify as not execution testable, no runtime
  bug invented.
- clean_control.py: should produce ZERO bugs. Any bug here is a false positive,
  the most important number for credibility. Report the false-positive rate.

Build a small confusion matrix from this (found vs expected per category). This
is new, high-value, and is what lets an examiner trust the ENVRI figures: you
have characterised QALLM's error behaviour on known ground truth.

---

## Step 2: ENVRI headline run (RQ1, the main result)

The verification gap at scale on real research notebooks. This is the figure
Chapter 5 is built around.

    python scripts/run_gap_experiment.py \
        --dataset datasets/envri_forest --output runs/envri_gap \
        --pattern "*.ipynb" --llm fedllm --rounds 5

Notes:

- Default retention is metrics_only, so ~289 notebooks will not flood the disk;
  the gap data lands in each session's summary and is aggregated.
- This is the long one. Run it under `nohup` or `tmux` so an SSH drop does not
  kill it:

      tmux new -s envri
      python scripts/run_gap_experiment.py --dataset datasets/envri_forest \
          --output runs/envri_gap --pattern "*.ipynb" --llm fedllm --rounds 5
      # Ctrl-b d to detach; tmux attach -t envri to return

- It is resumable: results stream to `results.jsonl` and already-done inputs are
  skipped, so if it stops you can rerun the same command to continue.

Outputs (in `runs/envri_gap/`):

- `aggregate.json`, the headline: verification_gap_rate with its bootstrap 95%
  confidence interval (and confirmation/verified-fix rates if present).
- `metrics.csv`, per-notebook rows for the appendix and any further stats.
- `results.jsonl`, the raw per-input record.
- `manifest.json`, the provenance (model, strategy, rounds, dataset, seed).

Report the gap rate as "point [ci_low, ci_high] at 95%", not a bare number.

---

## Step 3: ENVRI full RQ2 + RQ3 (confirmation and repair)

To report confirmation_rate and verified_fix_rate at scale, add `--confirm`.
This is more expensive (extra LLM calls per finding) and uses full retention,
so consider a representative subset first (e.g. copy ~50 notebooks into
`datasets/envri_forest_sub`) to gauge cost and time, then scale.

    python scripts/run_gap_experiment.py \
        --dataset datasets/envri_forest --output runs/envri_confirm \
        --pattern "*.ipynb" --llm fedllm --rounds 5 --confirm

Outputs as above; `aggregate.json` now carries confirmation_rate and
verified_fix_rate with their intervals.

Cost control: every run honours the budget caps; keep an eye on
`total_cost_usd` in the aggregate after the subset run before committing to the
full corpus.

---

## Step 4: HumanEvalFix validation and strategy comparison

The benchmark with known planted bugs. This produces the "RL (feedback)
outperforms oneshot and hypothesis" comparison with the significance test.

Pilot first (fast, confirms the benchmark downloads and runs):

    python scripts/run_humaneval.py \
        --output runs/heval_pilot \
        --oracle correctness \
        --models fedllm:gpt-oss-120b \
        --strategies feedback \
        --sample-size 20 --rounds 3 --seed 42

Then the full comparison across all three strategies:

    python scripts/run_humaneval.py \
        --output runs/heval_full \
        --oracle correctness \
        --models fedllm:gpt-oss-120b \
        --strategies rl,oneshot,hypothesis \
        --rounds 5 --seed 42

Outputs (in the output dir): `results.jsonl`, `aggregates.json`, `report.md`
with bug-detection and repair-success rates per strategy. The strategy
comparison plus the Wilcoxon test (from `qallm.stats`) is the basis for the
significance claim.

Optional, strengthens external validity (Tier 4 / future work): repeat with a
second model to show the result is not model-specific:

    python scripts/run_humaneval.py --output runs/heval_multimodel \
        --models fedllm:gpt-oss-120b,fedllm:gpt-oss-20b \
        --strategies rl,oneshot,hypothesis --rounds 5 --seed 42

---

## Step 5: a second ENVRI term (optional, breadth)

The corpus is term-scoped ("forest"). A second term shows the gap is not
domain-specific. Fetch and run another:

    python scripts/fetch_envri_dataset.py --term ocean --pages 21 \
        --output datasets/envri_ocean
    python scripts/run_gap_experiment.py --dataset datasets/envri_ocean \
        --output runs/envri_ocean_gap --pattern "*.ipynb" --llm fedllm --rounds 5

Report the two gap rates side by side; consistency across domains is a
robustness argument.

---

## What goes into Chapter 5

- The lab calibration confusion matrix and false-positive rate (Step 1):
  establishes that QALLM's findings are trustworthy and characterises its
  errors. Present this first; it earns the reader's trust in what follows.
- The ENVRI verification_gap_rate with its 95% CI (Step 2): the headline,
  "X% of functions that static analysis passed had a runtime defect, [lo, hi]
  at 95%, across N notebooks of real research code".
- The ENVRI confirmation_rate and verified_fix_rate with CIs (Step 3): closes
  RQ2 and RQ3.
- The HumanEvalFix strategy comparison with the significance test (Step 4):
  the "feedback/RL outperforms" result on known bugs.
- Optional breadth (Step 5) and multi-model (Step 4 optional) go in
  robustness / threats to validity.

## Practical reminders

- Run long jobs in tmux; they are resumable, so a drop is not fatal.
- Record model, date, and the `manifest.json` with every reported number;
  the ENVRI corpus drifts over time, so the manifest is the provenance.
- Watch `total_cost_usd` after each subset before scaling.
- Rotate the FedLLM key after the runs.
- The lab smoke test (Step 0) before each new run type catches breakage cheaply.
