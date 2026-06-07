#!/usr/bin/env bash
#
# QALLM environment setup (for running the pipeline and experiments directly,
# i.e. not in Docker). Idempotent: safe to run repeatedly.
#
# Usage:
#   ./scripts/setup.sh              # venv + base install
#   ./scripts/setup.sh --experiments  # also install the experiments extra
#
# After it finishes, activate the venv in your shell:
#   source .venv/bin/activate
#
# The prompt should then show (.venv) at the front, e.g.
#   (.venv) mohssin@nis05:~/qallm-uva$
#
# A script cannot activate the venv in your current shell for you (a child
# process cannot change its parent's environment), so the activate step is
# printed for you to run. Everything else is automated.

set -euo pipefail

# Run from the repository root regardless of where the script is invoked.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

WITH_EXPERIMENTS=0
for arg in "$@"; do
  case "$arg" in
    --experiments) WITH_EXPERIMENTS=1 ;;
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

# 1. Pick a Python. Prefer python3; require 3.10+.
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "ERROR: '$PYTHON' not found. Install Python 3.10+ or set PYTHON=..." >&2
  exit 1
fi
PY_VER="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "Using $PYTHON (Python $PY_VER)"

# 2. Create the venv if it does not exist (idempotent).
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment in .venv ..."
  "$PYTHON" -m venv .venv
else
  echo "Virtual environment .venv already exists; reusing it."
fi

# 3. Install into the venv's interpreter directly (no activation needed for
#    the install itself; activation is for your interactive shell afterwards).
VENV_PY=".venv/bin/python"
echo "Upgrading pip ..."
"$VENV_PY" -m pip install --upgrade pip >/dev/null

if [ "$WITH_EXPERIMENTS" -eq 1 ]; then
  echo "Installing QALLM with the experiments extra ..."
  "$VENV_PY" -m pip install -e ".[experiments]"
else
  echo "Installing QALLM (base) ..."
  "$VENV_PY" -m pip install -e .
fi

echo ""
echo "Setup complete."
echo ""
echo "Activate the environment in your shell now:"
echo ""
echo "    source .venv/bin/activate"
echo ""
echo "Your prompt should then start with (.venv). To run an experiment:"
echo ""
if [ "$WITH_EXPERIMENTS" -eq 1 ]; then
  echo "    python scripts/run_gap_experiment.py --dataset <dir> --output runs/gap --llm fedllm"
else
  echo "    (re-run with --experiments to enable the HumanEvalFix / dataset runs)"
fi
