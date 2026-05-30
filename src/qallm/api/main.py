"""QALLM Web API: FastAPI backend for the research pipeline UI.

This module is the thin assembler. The endpoints live in qallm.api.routers
(split by pipeline stage); shared infrastructure (the app, session store,
model catalog, helpers, logging) lives in qallm.api.core. Here we include
the routers and mount the frontend.

Endpoints map to the pipeline:
  Step 0: POST /api/session/upload       Upload files + init orchestrator
  Step 1: POST /api/analyse              Run static analysis
  Step 2: POST /api/repair/{sid}         LLM-based code repair
  Step 3: POST /api/verification/run     Iterative-feedback test generation
  Step 4: GET  /api/session/{sid}/stats  Full experiment statistics
  Obs:    GET  /api/session/{sid}/improvement  Per-round improvement audit
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from qallm.api.core import app
from qallm.api.routers import (
    analysis,
    config,
    experiments,
    experiments_control,
    repair,
    results,
    sessions as sessions_router,
    sessions_library,
    verification,
)

# Back-compat re-exports. Code and tests that did `from qallm.api.main
# import sessions` (the session dict) or the helpers keep working. The
# import alias above (sessions_router) avoids colliding the router module
# name with the sessions dict re-exported here.
from qallm.api.core import (  # noqa: E402,F401
    sessions,
    get_state as _get_state,
    parse_model_id as _parse_model_id,
    model_label as _model_label,
    check_model_available as _check_model_available,
    MODEL_CATALOG,
)

logger = logging.getLogger(__name__)

# Assemble the API from the per-stage routers.
app.include_router(sessions_router.router)
app.include_router(config.router)
app.include_router(analysis.router)
app.include_router(repair.router)
app.include_router(verification.router)
app.include_router(results.router)
app.include_router(experiments.router)
app.include_router(experiments_control.router)
app.include_router(sessions_library.router)


# ─── Favicon ────────────────────────────────────────────────────────
# Browsers request /favicon.ico unconditionally. When the frontend dist
# is mounted (deployed image) StaticFiles serves /favicon.svg, but the
# legacy /favicon.ico path and API-only mode (no dist) would still 404.
# This explicit route resolves both: it returns the bundled SVG favicon
# if present, or 204 No Content so the browser stops asking. It is
# declared before the catch-all static mount so it always wins.
@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.svg", include_in_schema=False)
def favicon():
    # Checked at request time, so referencing the module-level
    # _FRONTEND_DIST (defined below) and the source-tree fallback is safe.
    candidates = [
        _FRONTEND_DIST / "favicon.svg",
        Path(__file__).resolve().parents[2].parent
        / "web" / "frontend" / "public" / "favicon.svg",
    ]
    for path in candidates:
        if path.is_file():
            return FileResponse(str(path), media_type="image/svg+xml")
    return Response(status_code=204)


# ─── Frontend static files ──────────────────────────────────────────
# In a built/deployed image we serve the React app from the same process
# as the API. The dist directory is created by the Docker frontend build
# stage. In a local dev setup it usually doesn't exist (the developer
# runs `vite dev` separately on :5173), so we mount only if present.
#
# Path resolution: if QALLM_FRONTEND_DIST is set (Docker), trust it.
# Otherwise compute from the source tree, which only works for editable
# installs (`pip install -e .`). A non-editable install must set the
# env var because __file__ then points to site-packages, not the repo.

_env_dist = os.getenv("QALLM_FRONTEND_DIST")
if _env_dist:
    _FRONTEND_DIST = Path(_env_dist)
else:
    # Editable / source-tree fallback: src/qallm/api/main.py -> repo root -> web/dist
    _FRONTEND_DIST = Path(__file__).resolve().parents[2].parent / "web" / "dist"

if _FRONTEND_DIST.is_dir():
    # html=True makes FastAPI serve index.html for any unmatched path,
    # which is what the React SPA router needs to handle client-side
    # routes (e.g. /step/3) without hitting the API.
    app.mount(
        "/",
        StaticFiles(directory=str(_FRONTEND_DIST), html=True),
        name="frontend",
    )
    logger.info("Serving frontend static files from %s", _FRONTEND_DIST)
else:
    logger.info(
        "Frontend dist not found at %s; running API only "
        "(use `npm run dev` from web/frontend for local UI)",
        _FRONTEND_DIST,
    )
