# QALLM experiment protocol

This document is the reproducible protocol for the thesis evaluation. Its
purpose is that any reader, the author months from now, the daily supervisor,
or an examiner, can reproduce every number in the results chapter from the
persisted artefacts and the commands here. It records the environment, the
exact inputs, what each metric measures and its formula, how to run each
experiment, and how results are exported and aggregated.

Dashes are avoided as punctuation throughout, per the project convention.

## 1. What is being evaluated, and the claim

QALLM treats each static finding as a hypothesis and uses execution to
adjudicate it, then to verify repairs. The central empirical claim is that
execution-based assessment reveals defects that static analysis of
AI-generated notebook code misses (the verification gap), that individual
static findings can be confirmed or refuted by generated executed tests, and
that repairs can be proven by execution rather than asserted.

Three research questions, each answered by one metric (section 4):

- RQ1: To what extent does execution reveal defects static analysis misses?
- RQ2: How reliably can static findings be confirmed or refuted by execution?
- RQ3: When a repair is applied, can the fix be verified by execution, and how
  often does a repair that satisfies static analysis fail to fix the defect?

## 2. Two experiment tracks

The evaluation has two complementary tracks. They answer different questions
and should be reported separately.

1. **HumanEvalFix track** (controlled, labelled). Runs QALLM against the
   BigCode HumanEvalFix Python subset, where each problem has a known bug and
   a canonical fix. This gives bug-detection and repair-success rates against
   ground truth, and lets strategies and models be compared with significance
   tests. Protocol detail: `docs/experiments/humaneval.md`. Summarised in
   section 5 here.

2. **Verification-gap track** (realistic, unlabelled). Runs the full QALLM
   pipeline over real notebook code and produces the three execution-based
   metrics (verification gap, confirmation, verified-fix) via the metric
   export. This is the track that characterises the gap on AI-generated
   research code and yields the headline thesis figures. Detailed in
   sections 4 and 6.

The HumanEvalFix track validates that QALLM detects and fixes known bugs; the
verification-gap track measures what it finds on code with no answer key.

## 3. Environment and reproducibility

Record all of the following for any run; they belong in the results chapter so
a number can be traced to the exact conditions that produced it.

- **Code version**: the git commit hash (`git rev-parse --short HEAD`).
- **Python**: 3.10 or later (CI covers 3.10 and 3.12).
- **Install**: `pip install -e .` from the repo root.
- **Models**: the exact provider and model id for each role (see section 3.1).
- **Seed**: the sampling seed (default 42), recorded in the HumanEval manifest.
- **Budget caps**: rounds, tokens, seconds, cost (defaults in `qallm.config`).
- **Dataset slice**: which notebooks or which HumanEval sample and size.
- **Skipped units**: `units_skipped` from each session summary (empty and
  import-only files are filtered at ingestion and excluded from all metrics;
  report the count so denominators are interpretable).

Determinism caveat, stated plainly: LLM inference is not fully deterministic
even at temperature 0, so exact per-run numbers can vary between repetitions.
Report the model, seed, and commit; for the verification-gap track, prefer
aggregate rates over single-run point values, and consider repeating a sample
to show stability.

### 3.1 Models and providers

QALLM supports four providers behind one interface. For the thesis, the
relevant choices are:

- **FedLLM (EGI)**: free for VO users, OpenAI-compatible, GPU-backed hosted
  inference. Configure `FEDLLM_API_KEY`; default model `gpt-oss-120b`. This is
  the recommended provider for the full dataset run since it has no per-token
  cost. Confirm the model list for your VO first with
  `curl https://llm.ai.egi.eu/v1/models -H "Authorization: Bearer $FEDLLM_API_KEY"`.
- **OpenAI**: hosted, paid. Default `gpt-5-mini`. Useful as a comparison point.
- **Ollama**: local models (e.g. `gemma3:4b`), no API cost, needs local
  compute. Useful for a local-only comparison and for reproducibility without
  network access.
- **Anthropic**: hosted, paid. Available for comparison.

Separate models can be used for repair and test generation; record both when
they differ.

## 4. The three execution-based metrics (verification-gap track)

Authoritative definitions. These match `qallm.metrics_export` exactly; if the
code and this section ever disagree, the code in `metrics_export.py` is
canonical and this section is the bug.

All three exclude errored and discarded tests: only a test that ran and failed
is evidence of a defect. Each rate is null (not zero) when its denominator is
empty, so an unmeasured quantity is never reported as a measured zero.

### RQ1: verification gap rate

```
verification_gap_rate = execution_only / (confirmed_findings + execution_only)
```

- `execution_only`: count of execution-found bugs in functions that had no
  static finding. These are defects static analysis missed entirely.
- `confirmed_findings`: static findings whose enclosing function had an
  execution-found bug.
- Interpretation: of all execution-found defects, the share that no static
  tool flagged. This is the headline gap figure.

### RQ2: confirmation rate

```
confirmation_rate = confirmed / (confirmed + refuted)
```

- Over static findings whose type execution can test (reliability, security).
  Complexity and maintainability findings are properties of the source, not
  runtime behaviour, and are excluded as `not_execution_testable`.
- `confirmed`: a targeted test reproduced the finding (a reliability test that
  fails, or a security exploit that passes).
- `refuted`: the targeted test ran clean. Report refuted as a candidate false
  positive, with the caveat that not reproduced is not the same as proven
  absent.

### RQ3: verified-fix rate

```
verified_fix_rate = verified_fixed / (verified_fixed + not_fixed)
```

- Over confirmed findings re-tested after repair. Inconclusive results (the
  test errored on the repaired code, or there was no reproducing test) are
  excluded from the denominator.
- `verified_fixed`: the reproducing test shows the defect is gone (a
  reliability test that now passes, a security exploit that now fails).
- `not_fixed`: the defect survives on the repaired code. Report this
  separately: it is the case where a repair satisfied the static tool without
  fixing the underlying defect, which static-only pipelines would mark
  resolved. It is itself a finding.

### Aggregation

Across sessions, rates are recomputed from summed counts (count-weighted), not
averaged, so a session with one finding does not weigh equally with a session
with fifty. `aggregate_sessions` in `qallm.metrics_export` does this.

Each aggregate rate also carries a bootstrap 95% confidence interval
(`confidence_intervals` in the aggregate output). The interval is computed by
resampling sessions with replacement (sessions are the independent unit, since
findings cluster within them) and recomputing the pooled rate, so the headline
figures are reported as a point estimate with an interval rather than a bare
number. Report the interval alongside each rate in the results chapter.

## 5. HumanEvalFix track (summary)

Full detail in `docs/experiments/humaneval.md`. In brief:

- **Dataset**: BigCode `bigcode/humanevalpack`, Python subset, 164 problems,
  each with a known bug and canonical solution.
- **Metrics**: `bug_detection_rate` (QALLM flagged the known bug) and
  `repair_success_rate` (QALLM produced a fix passing the canonical tests),
  both verified by real pytest execution, errored runs excluded.
- **Comparisons**: across strategies (`feedback`, `oneshot`, `hypothesis`) and
  models, with Wilcoxon signed-rank pairwise significance and Cliff's delta
  (`qallm.stats`).

Pilot command (free, FedLLM):

```
python scripts/run_humaneval.py \
    --output runs/heval_pilot \
    --models fedllm:gpt-oss-120b \
    --strategies feedback \
    --sample-size 20 \
    --rounds 3 \
    --seed 42
```

Full command:

```
python scripts/run_humaneval.py \
    --output runs/heval_full \
    --models fedllm:gpt-oss-120b,ollama:gemma3:4b \
    --strategies feedback,oneshot,hypothesis \
    --rounds 5 \
    --seed 42
```

Outputs: `results.jsonl` (per-problem), `aggregates.json` (per cell of the
model x strategy grid), and `report.md`. The run is resumable.

## 6. Verification-gap track (full procedure)

This track produces the headline thesis numbers. It runs the full pipeline
over real notebook code and exports the three metrics.

### 6.1 Dataset

The target dataset is Yutong Li's collection (2,796 notebooks across 277
projects). Record exactly which subset is used and its size. Empty and
import-only files are filtered at ingestion; the per-session `units_skipped`
count records how many, and these are excluded from all metric denominators.

For a first run, use a small, named subset (for example one project or a fixed
list of N notebooks) to gauge latency and provider rate limits before the full
dataset.

### 6.2 Per-session run

For each notebook (or batch), run the pipeline with a fixed configuration. Use
the same strategy, oracle, rounds, judge, and model across the dataset so
sessions are comparable. Example:

```
qallm <notebook_or_dir> \
    --strategy feedback \
    --llm fedllm \
    --rounds 5 \
    --oracle crash \
    --judge-strategy lexicographic \
    --stage implementation
```

Each session persists its artefacts (per-round source, static findings,
verification results) and a `summary.json`. The verification gap is computed
from these artefacts and is always available after a run.

### 6.3 Confirm/refute and verify-fixes

The confirmation (RQ2) and verified-fix (RQ3) rates require generating and
running targeted tests, which use the LLM, so they are opt-in.

For a whole dataset in one command, pass `--confirm` to the batch runner
(section 6.6); it runs confirm/refute and verify-fixes for every session,
reconstructing their inputs from the persisted artefacts, and folds all three
rates into the aggregate. This is the recommended path for the thesis.

For a single session interactively, the web UI gap panel offers "Run
confirm/refute" and "Verify fixes" actions (backed by
`POST /api/session/{id}/confirm-findings` and
`POST /api/session/{id}/verify-fixes`), useful for inspecting one notebook in
detail.

### 6.4 Export and aggregate

Per session:

```
GET /api/session/{id}/metrics        # JSON, the full per-session record
GET /api/session/{id}/metrics.csv    # one-row CSV
```

Across the whole session library:

```
GET /api/metrics/aggregate           # count-weighted roll-up + per-session rows
```

The web UI gap panel also offers "Metrics JSON" and "Metrics CSV" download
buttons. Collect the per-session CSVs (or the aggregate) into the results
chapter. Every figure in Chapter 5 should be reproducible from these exports
plus the run configuration recorded per section 3.

### 6.5 Reporting checklist

For each reported number, record: commit hash, provider and model(s), strategy,
oracle, rounds, judge, seed (where applicable), dataset subset and size,
`units_skipped`, and whether confirm/verify were run. State which rates are
null (no denominator) rather than presenting them as zero.

### 6.6 One command for the whole track

`scripts/run_gap_experiment.py` runs the whole verification-gap track over a
dataset and writes `results.jsonl` (resumable), `aggregate.json`,
`metrics.csv`, and `manifest.json`.

```
# RQ1 only (free, no extra LLM calls): the verification-gap rate
python scripts/run_gap_experiment.py \
    --dataset data/li_notebooks --output runs/gap_full \
    --llm fedllm --rounds 5

# All three metrics (RQ1 + RQ2 + RQ3): adds confirm/refute and verify-fixes
python scripts/run_gap_experiment.py \
    --dataset data/li_notebooks --output runs/gap_full_confirmed \
    --llm fedllm --rounds 5 --confirm
```

With `--confirm`, the runner reconstructs the confirm/refute and verify-fixes
inputs from each session's artefacts (round 0 source for confirmation, the
final accepted source for verified fixes), so one invocation yields all three
aggregate rates. Without it, only the gap rate is computed. The aggregate is
count-weighted across sessions.

## 7. Threats to validity

- **Construct**: confirmation is corroboration at the targeted level, not
  per-line causation; refutation depends on the generator finding a triggering
  input, so a refuted finding is a candidate false positive, not a proven one;
  test-generation quality bounds what can be confirmed or verified.
- **Internal**: model nondeterminism; budget caps can truncate rounds (the
  halt reason is recorded in `summary.json`); the ERROR and discarded-test
  exclusions are deliberate and, by removing tests that never ran, make the
  gap rate conservative rather than inflated.
- **External**: notebook dataset representativeness; Python only; results are
  conditioned on the chosen model and may differ across providers (running
  more than one model addresses this partially).
- **Conclusion**: count-weighted aggregation is a choice (justified in section
  4); sample size and the number of repetitions bound the strength of any
  significance claim.

## 8. Quick reference

| Item | Where |
| --- | --- |
| HumanEvalFix protocol | `docs/experiments/humaneval.md` |
| Metric definitions (code) | `src/qallm/metrics_export.py` |
| Per-session metrics endpoint | `GET /api/session/{id}/metrics[.csv]` |
| Cross-session aggregate | `GET /api/metrics/aggregate` |
| Run mechanics (rounds, FROZEN+GROW, ERROR vs BUG) | `docs/run-mechanics-and-diagnostics.md` |
| Methodology decisions | `docs/methodology-decisions.md` |
| Thesis structure | `docs/thesis-draft-scaffold.md` |
