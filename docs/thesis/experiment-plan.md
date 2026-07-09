# QALLM experiment plan

> **Scope.** Authoritative for which runs exist and which RQ each answers. For
> metric definitions, formulas, environment, and threats, see
> `../experiments/protocol.md`. For copy-paste operator steps, see
> `../experiments/HOW-TO-RUN-EXPERIMENTS.md`. If commands disagree across these
> docs, this plan wins.

The experiments needed to answer the research questions, what each produces,
the exact command, and how it feeds the thesis. This is the empirical spine of
the evaluation chapter.

## Research questions

- **RQ1** How large is the verification gap, the proportion of functions that
  pass static analysis yet contain a defect that execution reveals?
- **RQ2** Of the defects static analysis does flag, how many does execution
  confirm versus refute?
- **RQ3** Of the defects found, how many can the pipeline produce a verified fix
  for (the repaired code passes the same execution check)?

A secondary, cross-cutting question runs through all three:

- **RQ-confidence** How trustworthy are the execution verdicts themselves?
  Answered by the mutation-based oracle confidence, reported alongside RQ1.

## The instrument: the lab dataset

Before any claim on real data, the pipeline is calibrated on `datasets/lab`, a
four-file set with a documented answer key (`datasets/lab/MANIFEST.md`):

| File | Purpose | Expected RQ1 (exec-only bugs) |
| --- | --- | --- |
| `reliability_gap.py` | 5 seeded wrong-value bugs | 5 |
| `clean_control.py` | negative control, correct code | 0 |
| `complexity_findings.py` | complex but correct | 0 |
| `security_findings.py` | Bandit-flagged security issues | 0 exec-only; findings confirm under RQ2 |

The lab set is not a result to report on its own; it is the evidence that the
measuring instrument is sound. The thesis cites it in the methodology and
threats-to-validity, not as a headline.

### E0: calibration run (instrument validation)

```
python scripts/run_gap_experiment.py \
    --dataset datasets/lab --output runs/lab_calibration \
    --pattern "*.py" \
    --llm fedllm --rounds 5 --oracle correctness --samples 1 \
    --workers 4 --confirm --mutation-confidence
```

Pass criteria: reliability 5/5, security 0 exec-only, clean/complexity at most a
small documented false positive on an under-specified function, security
findings confirm under RQ2, reliability bugs score high confidence. Produces the
calibration table and the strong-vs-weak confidence example for the methodology
chapter.

## The headline corpus: real research notebooks

The RQ1/RQ2/RQ3 numbers come from real Jupyter notebooks, the ENVRI corpus and,
for scale, Yutong Li's ~2,800 notebook dataset.

### E1: RQ1 headline (the verification gap on real code)

```
python scripts/run_gap_experiment.py \
    --dataset datasets/envri_forest --output runs/e1_rq1_headline \
    --pattern "*.ipynb" \
    --llm fedllm --rounds 5 --oracle correctness --samples 1 \
    --workers 4 --mutation-confidence
```

Produces the per-function defect counts and the run-level confidence
distribution (`aggregate.json` → `total_execution_only_bugs`,
`gap_confidence`). 

IMPORTANT, how to read the RQ1 number. The aggregate `verification_gap_rate` is
`execution_only_bugs / (confirmed_findings + execution_only_bugs)`. In an
RQ1-only run (`--confirm` off) `confirmed_findings` is always 0, so the rate is
trivially 1.0 and carries no information. The real RQ1 result is therefore the
COUNT story, not that ratio: how many execution-testable functions there were,
how many had an execution-only defect static analysis missed, and in how many
notebooks static analysis found nothing testable yet execution did. Report the
counts (and the per-function defect rate, execution-only bugs over testable
functions) for RQ1; the meaningful gap RATE comes from the `--confirm` run (E2),
where `confirmed_findings` is populated. Do not quote the 1.0 as a result.

Fast representative pass while the full run proceeds (sampling): add
`--sample 150 --sample-seed 42 --sample-stratify` to run a reproducible,
size-stratified subset. Compare the sampled counts to the full run once it
finishes to check the sample is representative.

Note: `--mutation-confidence` forces full retention. For the very large run,
consider two passes if disk is a constraint: one `--retention metrics_only` pass
for the counts, one `--mutation-confidence` pass on a `--sample` subset for the
confidence story.

### E2: RQ2 (confirm/refute of static findings) and the meaningful gap rate

```
python scripts/run_gap_experiment.py \
    --dataset datasets/envri_forest --output runs/e2_rq2 \
    --pattern "*.ipynb" \
    --llm fedllm --rounds 5 --oracle correctness --samples 1 \
    --workers 4 --confirm --mutation-confidence
```

Produces `total_confirmed`, `total_refuted`, `confirmation_rate`, AND the
meaningful `verification_gap_rate` (because `--confirm` populates
`confirmed_findings`, so the denominator is no longer degenerate). Interpreted
as: how often a static finding corresponds to a behaviour execution can
reproduce. A high refute rate is itself a finding (static analysis raising
issues execution cannot substantiate). This is the run that yields the gap rate
with its bootstrap CI for the thesis headline.

Fast pass: same `--sample 150 --sample-seed 42 --sample-stratify` flags.

### E3: RQ3 (verified-fix rate)

E3 is produced by the same `--confirm` run as E2 (`verified_fix_rate`,
`total_verified_fixed`, `total_not_fixed`). No separate command. It measures how
often the repair loop turns a found defect into code that passes the same
execution check. Report per EVERSE dimension where the sample allows.

### E4: scale and external validity (Li corpus)

```
python scripts/run_gap_experiment.py \
    --dataset datasets/li_notebooks --output runs/e4_scale \
    --pattern "*.ipynb" \
    --llm fedllm --rounds 5 --oracle correctness --samples 1 \
    --workers 4 --confirm --mutation-confidence
```

Repeat the E2 protocol on Yutong Li's ~2,800 notebooks once acquired, so the
headline gap rate (not the degenerate RQ1-only ratio) is what scales. Purpose:
show the gap rate is stable at scale and not an artifact of the ENVRI slice. For
a first look without waiting for the full corpus, run with
`--sample 300 --sample-seed 42 --sample-stratify`.

## Supporting analyses (not new runs)

- **Oracle-variance / consensus** (`docs/experiments/oracle-variance-and-consensus.md`):
  why single-sample is the calibrated setting and why union-consensus does not
  improve precision. Cited in threats to validity.
- **Generated-test quality**: `incoherent_oracles_dropped` per run, the measured
  backing for the soundness of the bug denominators (MD-002).
- **Provenance**: every run's `manifest.json` carries commit, model, environment,
  and dataset fingerprint, so each table traces to exact conditions.

## What each RQ needs, at a glance

| RQ | Run | Key output field | Reported as |
| --- | --- | --- | --- |
| RQ1 | E1 | `verification_gap_rate` + CI | gap rate with 95% CI, twice (all / high-confidence) |
| RQ2 | E2 | `confirmation_rate` | confirmed vs refuted, with refute interpretation |
| RQ3 | E3 (=E2 run) | `verified_fix_rate` | fixed vs not, per dimension if possible |
| RQ-conf | E1 | `gap_confidence.distribution` | confidence distribution over findings |
| validity | E0 | calibration table | instrument soundness (methodology) |
| scale | E4 | `verification_gap_rate` + CI | stability of the gap at scale |

## Execution checklist

1. E0 on the lab set, confirm pass criteria (instrument sound).
2. E1 on ENVRI for the headline gap rate + confidence.
3. E2/E3 on ENVRI for RQ2/RQ3 (one `--confirm` run yields both).
4. E4 on the Li corpus for scale, once the dataset is in hand.
5. Every run: keep `manifest.json`, `aggregate.json`, `metrics.csv`,
   `run.log`; archive under a stable path; cite the commit hash in the thesis.
