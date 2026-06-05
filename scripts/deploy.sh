#!/usr/bin/env bash
#
# deploy.sh: pull the latest code and (re)deploy QALLM on this server.
#
# Intended for the dev/staging VM. Run it by hand after merging to the
# tracked branch; it is deliberately not wired to any webhook or CI runner,
# so nothing external has access to this machine.
#
# Usage:
#   ./scripts/deploy.sh              # deploy the default branch (dev)
#   QALLM_BRANCH=main ./scripts/deploy.sh   # deploy a different branch/tag
#
# It is safe to re-run: it fast-forwards the tracked branch, rebuilds the
# image, restarts the container, and prunes the old image layer.

set -euo pipefail

# The branch (or tag) this server tracks. Override with QALLM_BRANCH.
BRANCH="${QALLM_BRANCH:-dev}"

# Resolve the repo root from this script's location, so the script works
# regardless of the current working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_DIR}"

echo "==> Deploying QALLM from branch '${BRANCH}' in ${REPO_DIR}"

# Refuse to deploy on top of uncommitted local changes: on a shared box,
# silent overwrites are worse than a clear stop.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: working tree has uncommitted changes. Commit or stash first." >&2
  exit 1
fi

# A .env with real API keys must exist before we build; the app needs it.
if [ ! -f .env ]; then
  echo "ERROR: .env not found. Copy .env.example to .env and set your keys." >&2
  exit 1
fi

echo "==> Fetching and fast-forwarding ${BRANCH}"
git fetch origin --prune
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}"

CURRENT="$(git rev-parse --short HEAD)"
echo "==> Now at ${CURRENT}"

echo "==> Building and restarting the container"
docker compose up -d --build

echo "==> Pruning dangling images"
docker image prune -f >/dev/null 2>&1 || true

# Give the API a moment, then check health so a broken deploy fails loudly.
echo "==> Waiting for the API to come up"
PORT="${API_PORT:-8000}"
for i in $(seq 1 30); do
  if curl -fsS "http://localhost:${PORT}/api/health" >/dev/null 2>&1; then
    echo "==> Healthy. Deployed ${BRANCH} @ ${CURRENT} on port ${PORT}."
    exit 0
  fi
  sleep 2
done

echo "ERROR: API did not report healthy within 60s. Check: docker compose logs" >&2
exit 1
