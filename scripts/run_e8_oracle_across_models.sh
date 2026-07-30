#!/usr/bin/env bash
# =============================================================================
# run-e8-oracle-across-models.sh   (v2, CORRECTED against the real CLI)
#
# Nafis comment E8: "How multiple LLM improves crash and correctness oracle and
# if possible, compare with other work."
#
# -----------------------------------------------------------------------------
# WHY v2 EXISTS
#
# v1 of this script would have failed at the first command. I wrote it before
# reading your CLI and guessed the flag names. Having now read the repository:
#
#   * There is no `qallm run` subcommand. The CLI is `qallm <source> [flags]`,
#     and experiments run through scripts/run_humaneval.py and
#     scripts/run_gap_experiment.py.
#   * There is no --benchmark, --limit, --out, --from-manifest or --resume.
#     The real names are --output, --sample-size, --dataset, --sample.
#   * --models on run_humaneval.py is one COMMA-SEPARATED string of
#     provider:model pairs, e.g. "fedllm:gpt-oss-120b,openai:gpt-5-mini".
#   * --strategies is plural, values feedback|rl|oneshot|hypothesis, where rl is
#     a back-compat alias for feedback.
#   * NEITHER runner accepts a cost cap. --max-cost-usd exists only on the main
#     qallm CLI. That matters for an overnight paid run; stage 0 handles it.
#
# Because there is no --resume, resumability is per arm: each arm gets its own
# output directory and a .done marker, and re-running skips completed arms. A
# crash costs one arm, not the night.
#
# Usage:
#   ./run-e8-oracle-across-models.sh smoke      # stage 0, ~10 min, prices the run
#   ./run-e8-oracle-across-models.sh corpus     # stage 1, ~30 min
#   ./run-e8-oracle-across-models.sh benchmark  # stage 2, overnight
#
# Run inside tmux.
# =============================================================================

set -Eeuo pipefail

# ----------------------------------------------------------------- configuration
REPO_ROOT="${REPO_ROOT:-$HOME/qallm-uva}"
RUN_TAG="${RUN_TAG:-e8_oracle_x_model}"
OUT_ROOT="${OUT_ROOT:-$REPO_ROOT/runs/$RUN_TAG}"

SEED=42
ROUNDS=5
WORKERS="${WORKERS:-8}"
STRATEGY="feedback"          # held fixed; the panel varies the model
JUDGE="lexicographic"        # the thesis default
STAGE_PROFILE="implementation"
SMOKE_N=4                    # problems per arm in stage 0, purely to price it

# provider:model, exactly the form run_humaneval.py --models expects.
HEADLINE="fedllm:gpt-oss-120b"                 # free, EGI-hosted
PAID=("openai:gpt-5-mini" "openai:gpt-5.4-mini" "openai:gpt-5.6-luna")
ALL_MODELS=("$HEADLINE" "${PAID[@]}")
ORACLES=("crash" "correctness")

# Stage 1 reuses the corpus the cross-model panel already ran under the
# correctness oracle, so the new crash arms are comparable rather than similar.
CORPUS_DATASET="${CORPUS_DATASET:-$REPO_ROOT/datasets/envri_forest}"
CORPUS_SAMPLE=40

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*" | tee -a "$OUT_ROOT/driver.log"; }
die() { printf '[%s] FATAL %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; exit 1; }

slug()      { printf '%s' "${1//[:\/]/_}"; }
arm_dir()   { printf '%s/%s' "$OUT_ROOT" "$1"; }
is_done()   { [[ -f "$(arm_dir "$1")/.done" ]]; }
mark_done() { date -u +%FT%TZ > "$(arm_dir "$1")/.done"; }

cost_of() {  # sum cost_usd recorded under a directory
  python3 - "$1" <<'PY'
import json, sys
from pathlib import Path
tot = 0.0
for res in Path(sys.argv[1]).rglob("results.json"):
    try:
        blob = json.loads(res.read_text())
    except Exception:
        continue
    recs = blob if isinstance(blob, list) else blob.get("results", [])
    tot += sum(float(r.get("cost_usd") or 0.0) for r in recs if isinstance(r, dict))
print(f"{tot:.2f}")
PY
}

# ----------------------------------------------------------------- preflight
preflight() {
  mkdir -p "$OUT_ROOT"
  cd "$REPO_ROOT" || die "REPO_ROOT $REPO_ROOT not found"
  [[ -f scripts/run_humaneval.py ]] || die "scripts/run_humaneval.py missing; wrong REPO_ROOT?"
  python3 -c "import qallm" 2>/dev/null \
    || die "qallm not importable. Activate the venv, or pip install -e . --break-system-packages"

  if [[ -n "$(git status --porcelain)" ]]; then
    die "working tree is dirty. Commit or stash first: every number in the thesis is pinned to a commit, and an untracked change makes the manifest a fiction."
  fi
  local commit branch
  commit="$(git rev-parse HEAD)"; branch="$(git rev-parse --abbrev-ref HEAD)"
  log "repo $branch @ ${commit:0:12}"
  printf '{"run_tag":"%s","commit":"%s","branch":"%s","started":"%s","seed":%d,"rounds":%d,"strategy":"%s","judge":"%s"}\n' \
    "$RUN_TAG" "$commit" "$branch" "$(date -u +%FT%TZ)" "$SEED" "$ROUNDS" "$STRATEGY" "$JUDGE" \
    > "$OUT_ROOT/driver-provenance.json"
  [[ -n "${OPENAI_API_KEY:-}" ]] || die "OPENAI_API_KEY unset; the paid arms need it."
  log "preflight ok"
}

# ----------------------------------------------------------------- stage 0
# Purpose is not results. It is proving the flags and models work, and PRICING
# stage 2, because neither runner has a cost cap. The per-problem cost_usd in
# results.json makes the projection exact rather than a guess.
stage_smoke() {
  log "STAGE 0 smoke: $SMOKE_N problems per arm, to validate and to price"
  local models_csv arm
  models_csv="$(IFS=,; echo "${ALL_MODELS[*]}")"
  for o in "${ORACLES[@]}"; do
    arm="smoke__${o}"
    mkdir -p "$(arm_dir "$arm")"
    log "  $arm  (all four models in one invocation)"
    if ! python3 scripts/run_humaneval.py \
          --output "$(arm_dir "$arm")" \
          --models "$models_csv" \
          --strategies "$STRATEGY" \
          --sample-size "$SMOKE_N" \
          --seed "$SEED" \
          --rounds 2 \
          --oracle "$o" \
          --judge-strategy "$JUDGE" \
          --workers 2 \
          --log-level INFO \
          > "$(arm_dir "$arm")/stdout.log" 2>&1; then
      log "  FAILED. Last 30 lines:"
      tail -30 "$(arm_dir "$arm")/stdout.log" | sed 's/^/    /'
      die "stage 0 failed. Fix before spending a night: python3 scripts/run_humaneval.py --help"
    fi
  done

  log ""
  log "Projected cost of stage 2, from the cost_usd actually recorded above:"
  python3 - "$OUT_ROOT" 164 "$ROUNDS" <<'PY'
import json, sys
from pathlib import Path
root, n_full, rounds = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
per = {}
for res in root.glob("smoke__*/**/results.json"):
    try:
        blob = json.loads(res.read_text())
    except Exception:
        continue
    recs = blob if isinstance(blob, list) else blob.get("results", [])
    for r in recs:
        if isinstance(r, dict):
            per.setdefault(r.get("model", "?"), []).append(float(r.get("cost_usd") or 0.0))
if not per:
    print("  no cost_usd found in results.json; price it from your provider dashboard instead")
    raise SystemExit(0)
total = 0.0
for m, costs in sorted(per.items()):
    mean = sum(costs) / len(costs)
    proj = mean * n_full * (rounds / 2)
    print(f"  {m:28s} mean ${mean:7.4f}/problem  ->  ${proj:8.2f} per oracle arm"
          + ("   (free)" if mean == 0.0 else ""))
    if mean:
        total += proj * 2
print(f"  {'PROJECTED PAID TOTAL':28s} {'':24s}      ${total:8.2f} for stage 2")
print("  The 2-round to %d-round scale-up is linear here. That overestimates if runs" % rounds)
print("  converge early and underestimates if they do not, so treat it as an order")
print("  of magnitude and stop the run if it exceeds what you agreed.")
PY
  log ""
  log "Decide on that number before stage 2. Neither runner enforces a cap, so the"
  log "only cap is you watching it or a limit set at the provider."
}

# ----------------------------------------------------------------- stage 1
stage_corpus() {
  log "STAGE 1 corpus: 4 models x crash oracle, $CORPUS_SAMPLE notebooks"
  [[ -d "$CORPUS_DATASET" ]] || die "dataset $CORPUS_DATASET not found; set CORPUS_DATASET"
  local arm provider model
  for pm in "${ALL_MODELS[@]}"; do
    provider="${pm%%:*}"; model="${pm#*:}"
    arm="corpus__$(slug "$pm")__crash"
    if is_done "$arm"; then log "  skip $arm (done)"; continue; fi
    mkdir -p "$(arm_dir "$arm")"
    log "  $arm"
    python3 scripts/run_gap_experiment.py \
      --dataset "$CORPUS_DATASET" \
      --output "$(arm_dir "$arm")" \
      --llm "$provider" \
      --model "$model" \
      --strategy "$STRATEGY" \
      --rounds "$ROUNDS" \
      --workers "$WORKERS" \
      --oracle crash \
      --judge-strategy "$JUDGE" \
      --stage "$STAGE_PROFILE" \
      --pattern '*.ipynb' \
      --sample "$CORPUS_SAMPLE" \
      --sample-seed "$SEED" \
      --mutation-confidence \
      --confirm \
      --retention full \
      --log-level INFO \
      --log-file "$(arm_dir "$arm")/run.log" \
      > "$(arm_dir "$arm")/stdout.log" 2>&1
    mark_done "$arm"
    log "  $arm complete"
  done
  log "STAGE 1 complete"
}

# ----------------------------------------------------------------- stage 2
# One invocation per (model, oracle). Slower to launch than batching models, but
# with no --resume a crash then costs one cell instead of six. The headline
# model's two cells already exist as the Feedback row of tab:ablation, so only
# the three paid models run here.
stage_benchmark() {
  log "STAGE 2 benchmark: 3 paid models x 2 oracles, 164 HumanEvalFix problems"
  local arm
  for pm in "${PAID[@]}"; do
    for o in "${ORACLES[@]}"; do
      arm="bench__$(slug "$pm")__${o}"
      if is_done "$arm"; then log "  skip $arm (done)"; continue; fi
      mkdir -p "$(arm_dir "$arm")"
      log "  $arm starting"
      python3 scripts/run_humaneval.py \
        --output "$(arm_dir "$arm")" \
        --models "$pm" \
        --strategies "$STRATEGY" \
        --seed "$SEED" \
        --rounds "$ROUNDS" \
        --oracle "$o" \
        --judge-strategy "$JUDGE" \
        --workers "$WORKERS" \
        --log-level INFO \
        > "$(arm_dir "$arm")/stdout.log" 2>&1
      mark_done "$arm"
      log "  $arm complete, cost so far \$$(cost_of "$(arm_dir "$arm")")"
    done
  done
  log "STAGE 2 complete. Total paid cost \$$(cost_of "$OUT_ROOT")"
}

summarise() {
  log ""
  log "Arms in $OUT_ROOT:"
  for d in "$OUT_ROOT"/*/; do
    [[ -d "$d" ]] || continue
    printf '  %-46s %s\n' "$(basename "$d")" \
      "$([[ -f "$d/.done" ]] && echo '[done]' || echo '[incomplete]')" \
      | tee -a "$OUT_ROOT/driver.log"
  done
  log ""
  log "Next: python3 analyse-e8.py --root $OUT_ROOT --prefix bench --latex"
}

main() {
  local what="${1:-smoke}"
  mkdir -p "$OUT_ROOT"
  preflight
  case "$what" in
    smoke)     stage_smoke ;;
    corpus)    stage_corpus ;;
    benchmark) stage_benchmark ;;
    all)       stage_smoke; stage_corpus; stage_benchmark ;;
    *)         die "unknown stage '$what'. Use smoke, corpus, benchmark, or all." ;;
  esac
  summarise
  log "driver finished"
}

main "$@"
