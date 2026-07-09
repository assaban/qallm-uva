# Running QALLM directly (venv) for experiments

The Docker image is the easiest way to run the web app, but for the
experiments (HumanEvalFix and the verification-gap dataset runs) it is usually
simpler to run QALLM directly in a Python virtual environment on the machine,
so you can point at local notebook directories and watch progress in the
terminal. This is the setup for that path.

> **Scope.** Environment setup only. The experiment steps themselves live in
> `../experiments/HOW-TO-RUN-EXPERIMENTS.md`; which runs matter for the thesis
> is defined in `../thesis/experiment-plan.md`.

## One-time setup

From the repository root:

```
./scripts/setup.sh --experiments
```

This is idempotent (safe to re-run). It creates a `.venv`, upgrades pip, and
installs QALLM with the experiments extra (`pip install -e ".[experiments]"`,
which pulls in the `datasets` package needed for HumanEvalFix). Use it without
`--experiments` if you only need the base pipeline.

## Activate the environment

A script cannot change your current shell's environment, so activation is one
manual step you run yourself:

```
source .venv/bin/activate
```

Your prompt should then start with `(.venv)`, for example:

```
(.venv) mohssin@nis05:~/qallm-uva$
```

That confirms you are inside the virtual environment. Everything below assumes
the environment is active.

## Run an experiment

Verification-gap track over a local notebook dataset (the thesis figures):

```
# pilot first to gauge latency and rate limits
python scripts/run_gap_experiment.py \
    --dataset data/notebooks_pilot --output runs/gap_pilot \
    --llm fedllm --rounds 3

# all three metrics (RQ1 + RQ2 + RQ3) in one run
python scripts/run_gap_experiment.py \
    --dataset data/li_notebooks --output runs/gap_full \
    --llm fedllm --rounds 5 --confirm

# parallel: each file is an independent session, so files can run concurrently
python scripts/run_gap_experiment.py \
    --dataset data/li_notebooks --output runs/gap_full \
    --llm fedllm --rounds 5 --confirm --workers 4
```

`--workers N` (default 1, sequential) processes N files concurrently in
separate processes. Each file is its own orchestrator and session, so this is
safe; the run stays resumable (completed files are skipped) and the aggregate
is order-independent. The practical ceiling is the LLM API's concurrency limit,
not CPU: for FedLLM, start at 4 and watch for rate-limit warnings before going
higher. With `metrics_only` retention this gives a near-linear speedup on large
datasets.

Under `--workers N`, each worker logs to the same `run.log` (and stderr) with a
`[pid NNNN]` prefix, so a parallel run is observable live (`tail -f run.log`)
and interleaved lines stay attributable to their worker. Each completed file
also logs a `Progress: k/total (pct%)` line, counted against the whole run
(already-done on resume plus this run's pending), so the true position in the
dataset is visible (`tail -f run.log | grep Progress`). Control verbosity with
`--log-level` (DEBUG for per-step detail, WARNING to quieten); it applies to the
workers too.

To get a representative signal fast while a full run is still going, sample the
dataset: `--sample N` runs a random subset of N files, `--sample-seed S` makes
the subset reproducible (so a sampled run can be cited and repeated), and
`--sample-stratify` buckets files by size into small/medium/large and samples
proportionally so the subset spans the size range rather than over-representing
one band. `--sample 0` (the default) runs everything. Example, a 150-file
stratified pilot:

```
python scripts/run_gap_experiment.py \
    --dataset datasets/envri_forest --output runs/pilot --pattern "*.ipynb" \
    --llm fedllm --rounds 5 --oracle correctness --samples 1 --workers 4 \
    --mutation-confidence --sample 150 --sample-seed 42 --sample-stratify
```

`--mutation-confidence` adds a soundness check to each gap finding: after the
gap is measured, the oracle for each execution-only function is mutation-tested
(small faults are injected into the function and the generated suite is checked
for whether it catches them), yielding a per-function confidence
(high/medium/low) and an aggregate distribution. It reads round-0 artefacts from
disk, so it forces full retention, and it scores only gap functions, so the cost
is proportional to the number of findings. Use it for the headline run to report
the gap rate alongside its confidence distribution.

By default a batch gap run uses `--retention metrics_only`: it keeps the gap
data in `summary.json` and skips the per-unit round directories, which is far
less disk on a large dataset (those directories are one folder per code unit
per round). Pass `--retention full` to keep every variant's provenance for
deep inspection. Note `--confirm` forces `full` automatically, because
confirm/refute and verify-fixes reconstruct their inputs from the per-round
artefacts on disk.

HumanEvalFix validation track:

```
python scripts/run_humaneval.py \
    --output runs/heval_pilot \
    --models fedllm:gpt-oss-120b \
    --strategies feedback \
    --sample-size 20 --rounds 3 --seed 42
```

See `docs/experiments/protocol.md` for what each run measures and how to
report it.

## Credentials

Hosted models need credentials in the environment (or a `.env` file the app
loads). FedLLM is free for VO users; set `FEDLLM_API_KEY`. Confirm the model
list for your VO before a long run:

```
curl https://llm.ai.egi.eu/v1/models -H "Authorization: Bearer $FEDLLM_API_KEY"
```

## Troubleshooting

- `(.venv)` not in your prompt: you have not activated the environment in this
  shell. Re-run `source .venv/bin/activate`.
- `ModuleNotFoundError: No module named 'datasets'`: the experiments extra is
  not installed. Re-run `./scripts/setup.sh --experiments` (or
  `pip install -e ".[experiments]"` with the venv active).
- A new shell or SSH session does not keep the activation; re-activate per
  session, or add the `source` line to your shell profile on the VM.
