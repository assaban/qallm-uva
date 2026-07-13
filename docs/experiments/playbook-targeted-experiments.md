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

## 4. Notebook vs plain Python (one variable: --pattern)
The forest and ocean corpora contain BOTH forms from the same repositories
(forest: 2,034 .ipynb and 3,084 .py; ocean: 1,544 .ipynb and 1,303 .py), so the
comparison is naturally controlled: same projects, same authors, same domain,
only the code form differs. Plain .py files are self-contained by construction
relative to notebook cells, so this run decomposes the verification gap: a gap
that persists on .py is not an extraction artefact; a gap that drops measures
the notebook-form fragility share. Pairs against the ablation's correctness arm
(same corpus, seed, and commit; one variable):

    python scripts/run_gap_experiment.py \
      --dataset datasets/envri_forest --output runs/x_form_forest_py \
      --pattern "*.py" --llm fedllm --rounds 5 --oracle correctness \
      --samples 1 --workers 4 --confirm --mutation-confidence \
      --sample 40 --sample-seed 42 --log-level INFO \
      --exclude "*/tests/*" --exclude "*/test/*" --exclude "test_*.py" \
      --exclude "*_test.py" --exclude "__init__.py" --exclude "setup.py" \
      --exclude "conftest.py" --exclude "conf.py"

The excludes are sampling-frame hygiene, not optional (MD-010): 45% of the
raw .py trees are test files, __init__.py, and packaging boilerplate with no
notebook counterpart (raw 3,084 forest / 1,303 ocean; authored analysis code
after excludes: 1,354 / 1,073). The exclusion list is recorded in the run
manifest. \
      2>&1 | tee runs/x_form_forest_py/run.log

Reading caveats (state in any write-up): the seeded 40 .py files are different
files than the 40 notebooks (population-level comparison, no per-file pairing);
repo .py files skew toward utility modules; some are scripts with __main__
blocks. Optional completion: the same run on datasets/envri_ocean gives a 2x2
(domain x form) table.

## Launch order (after the headline runs finish)
1. Oracle ablation pair: forest crash, then forest correctness (same commit,
   no git pull between; back to back).
2. Cross-domain: ocean .ipynb (the forest arm comes free from step 1).
3. Form comparison: forest .py (pairs against step 1's correctness arm).
4. Optional: ocean .py, completing the 2x2.
Six seeded runs total; one variable per comparison; record the commit per run
and check manifest.json shows dirty: false.

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
