# QALLM experiment plan

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
    --dataset datasets/envri --output runs/e1_rq1 \
    --pattern "*.ipynb" \
    --llm fedllm --rounds 5 --oracle correctness --samples 1 \
    --workers 4 --retention metrics_only --mutation-confidence
```

Produces: the gap rate with its bootstrap 95% CI (`aggregate.json` →
`verification_gap_rate` and `confidence_intervals`), plus the run-level
confidence distribution (`gap_confidence`). Report the gap rate twice, over all
findings and restricted to high-confidence findings; if close, that is direct
evidence the gap is real and not test noise. This is the central result of the
thesis.

Note: `--mutation-confidence` forces full retention, so for the very large run,
consider a two-pass approach, one `metrics_only` pass for the headline rate, one
`--mutation-confidence` pass on a representative subset for the confidence story,
if disk is a constraint.

### E2: RQ2 (confirm/refute of static findings)

```
python scripts/run_gap_experiment.py \
    --dataset datasets/envri --output runs/e2_rq2 \
    --pattern "*.ipynb" \
    --llm fedllm --rounds 5 --oracle correctness --samples 1 \
    --workers 4 --confirm
```

Produces: `total_confirmed`, `total_refuted`, `confirmation_rate`. Interpreted
as: how often a static finding corresponds to a behaviour execution can
reproduce. A high refute rate is itself a finding (static analysis raising
issues execution cannot substantiate).

### E3: RQ3 (verified-fix rate)

E3 is produced by the same `--confirm` run as E2 (`verified_fix_rate`,
`total_verified_fixed`). It measures how often the repair loop turns a found
defect into code that passes the same execution check. Report per EVERSE
dimension where the sample allows.

### E4: scale and external validity (Li corpus)

Repeat E1 on Yutong Li's ~2,800 notebooks once acquired. Purpose: show the gap
rate is stable at scale and not an artifact of the smaller ENVRI slice. Same
command, larger `--dataset`.

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
