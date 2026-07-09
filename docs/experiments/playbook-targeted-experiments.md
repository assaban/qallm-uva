# Playbook: targeted comparison experiments

How to run bounded, comparable experiments without full-corpus cost. The key
mechanism is the seeded sample: `--sample 40 --sample-seed 42` selects the SAME
40 notebooks every time, so two runs differing in exactly one variable are a
controlled comparison. Change one flag per experiment; keep the seed fixed.

Common base (corpus comparisons):

    BASE="python scripts/run_gap_experiment.py --pattern '*.ipynb' \
      --rounds 5 --samples 1 --workers 4 --confirm --mutation-confidence \
      --sample 40 --sample-seed 42 --log-level INFO"

## 1. Cross-model (one variable: the model)

    $BASE --dataset datasets/envri_forest --llm fedllm \
      --output runs/x_model_fedllm
    $BASE --dataset datasets/envri_forest --llm openai --model gpt-4o-mini \
      --output runs/x_model_gpt4omini

## 2. Cross-domain (one variable: the corpus term)

    python scripts/fetch_envri_dataset.py --term ocean --pages 21 \
      --output datasets/envri_ocean
    $BASE --dataset datasets/envri_forest --llm fedllm --output runs/x_dom_forest
    $BASE --dataset datasets/envri_ocean  --llm fedllm --output runs/x_dom_ocean

## 3. Oracle ablation (one variable: the oracle)

    $BASE --dataset datasets/envri_forest --llm fedllm --oracle crash \
      --output runs/x_oracle_crash
    $BASE --dataset datasets/envri_forest --llm fedllm --oracle correctness \
      --output runs/x_oracle_correctness

## 4. Notebook vs plain Python (one variable: the code form)
The corpus is .ipynb; HumanEvalFix is .py. Self-containedness defects should
appear only on the notebook side, which decomposes the gap by defect class.

## 5. HumanEvalFix (external ground truth): USE THE DEDICATED RUNNER
Do NOT use run_gap_experiment.py for this. The benchmark has its own runner and
its own document; read docs/experiments/humaneval.md for the full rationale,
metrics, and cost notes. Short form:

    pip install -e ".[experiments]"     # once; installs HF datasets
    python scripts/run_humaneval.py \
      --output runs/heval_$(date +%Y%m%d) \
      --models fedllm:gpt-oss-120b \
      --strategies feedback,oneshot,hypothesis \
      --rounds 5 --workers 6 --seed 42

Resumable: re-running the same command skips completed combinations.

## Reading any comparison
Each corpus run's aggregate.json carries the same fields: measured, gap
defects, confidence distribution, confirmations (reliability/static split),
verified-fix rate with CI. Check manifest.json shows dirty: false and record
the commit per run. HumanEvalFix writes its own results.jsonl per combination.
