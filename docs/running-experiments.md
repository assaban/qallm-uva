# Running QALLM directly (venv) for experiments

The Docker image is the easiest way to run the web app, but for the
experiments (HumanEvalFix and the verification-gap dataset runs) it is usually
simpler to run QALLM directly in a Python virtual environment on the machine,
so you can point at local notebook directories and watch progress in the
terminal. This is the setup for that path.

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
```

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
