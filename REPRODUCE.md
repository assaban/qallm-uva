# Reproducing the thesis results

Every number in the thesis maps to a run directory, a command, and a manifest.
This file is that map. Each run writes `manifest.json` (commit, branch, dirty
flag, untracked count, dataset fingerprint, configuration), `aggregate.json`
(the numbers), `metrics.csv` (per-session), and `results.jsonl` (per-notebook
detail). The precedence rule for conflicts: code > methodology log
(`docs/thesis/methodology-decisions.md`) > other docs.

## Environment

    git clone -b dev https://github.com/assaban/qallm-uva.git && cd qallm-uva
    python -m venv .venv && source .venv/bin/activate
    pip install -e . --break-system-packages
    export FEDLLM_API_KEY=...   # all headline runs use FedLLM (gpt-oss-120b), free

Bandit, Radon, and Ruff install with the package; TruffleHog is an optional
external binary (secret scanning is skipped gracefully without it).

## The corpus

The ENVRI forest corpus (1,843 notebooks) is assembled from the ENVRI notebook
catalogue; results change over time, so the fetch records term, pages, and date:

    python scripts/fetch_envri_dataset.py --term forest --pages 43 \
      --output datasets/envri_forest

## The runs behind the thesis numbers

### Calibration (instrument validation; Experiments, calibration section)
5/5 seeded reliability defects recovered; 7 confirmed; verified-fix 5/7; all
gap defects high mutation confidence; 0 errored inputs.

    python scripts/run_gap_experiment.py --dataset datasets/lab \
      --output runs/lab_check --pattern "*.py" --llm fedllm --rounds 5 \
      --oracle correctness --samples 1 --confirm --mutation-confidence

### E2 full characterisation (RQ1, RQ2 headline; Experiments chapter)
1,826 measured of 1,843 (17 malformed JSON, reported not hidden); 41,978 units;
2,286 static findings; 806 execution-only defects (550 high confidence, 68.2%);
verified-fix 470/749 = 62.8%, 95% CI [58.3%, 67.2%]; 267 security findings
inconclusive by design; 631 not execution-testable.

    python scripts/run_gap_experiment.py --dataset datasets/envri_forest \
      --output runs/e2_full --pattern "*.ipynb" --llm fedllm --rounds 5 \
      --oracle correctness --samples 1 --workers 4 --confirm \
      --mutation-confidence --log-level INFO 2>&1 | tee runs/e2_full/run.log

Numbers vary a few points run to run (LLM generation variance); the verified-fix
rate stays within its CI. The gap and confirmation RATES are degenerate on this
corpus and are deliberately not reported (thesis, hardening section).

### Seeded 40-notebook sample (fix verification; reproducible subset)
Same command as E2 plus: `--sample 40 --sample-seed 42`.

### Benchmark ground truth (HumanEval) and oracle ablation
HumanEvalFix: uses the dedicated runner, not the gap runner; see
`docs/experiments/humaneval.md` and `scripts/run_humaneval.py`
(`pip install -e ".[experiments]"` once, then
`python scripts/run_humaneval.py --output runs/heval --models
fedllm:gpt-oss-120b --strategies feedback,oneshot,hypothesis --rounds 5
--workers 6 --seed 42`).
Ablation: the seeded sample under `--oracle crash` vs `--oracle correctness`.

## Verifying a run's provenance

    python3 -c "import json; m=json.load(open('runs/<run>/manifest.json')); \
      g=m['provenance']['git']; print(g['commit'][:10], 'dirty:', g['dirty'])"

`dirty` reflects tracked-file modifications only; untracked data files are
counted separately (`untracked`). A citable run has `dirty: false`.

## Per-defect evidence

Every session persists full lineage under the sessions directory:
`reports/<session>/lineage/round_NN/<unit>/` with `source.py`, `tests/`,
`static.json`, `verification.json`, `judge.json`. The worked examples in the
thesis (Experiments, "Anatomy of a verdict") are auditable from these artefacts.
