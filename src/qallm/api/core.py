"""Shared API infrastructure: the app, session state, model catalog, helpers.

Extracted from the former monolithic ``api/main.py`` so the endpoint
modules in ``api/routers/`` can share one app instance and one session
store without import cycles. ``main.py`` is now a thin assembler that
imports the routers and mounts the frontend.

Nothing here changes behaviour; it is the same objects and functions that
lived at the top of main.py, moved to a module the routers can import.
"""

from __future__ import annotations

import logging
import os
from typing import Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from qallm.config import settings

logger = logging.getLogger(__name__)

# ─── Logging setup ──────────────────────────────────────────────────
# Without this, Python's default WARNING level silences every
# logger.info() across the orchestrator, verification manager, repair
# manager, and LLM providers, making the running pipeline opaque to
# operators. Honour LOG_LEVEL so deployments can tune verbosity.
_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
# Uvicorn replaces handlers when it boots, so force-set the root level
# after basicConfig to survive uvicorn's reconfiguration.
logging.getLogger().setLevel(_log_level)


class _NoPollingAccessLog(logging.Filter):
    """Drop uvicorn access lines for high-frequency polling paths.

    The frontend polls /api/jobs/{id} every 500ms during long jobs;
    without this filter those polls flood the log and bury the
    orchestrator's diagnostic output. Audit-worthy requests (uploads,
    analyse, repair, verification submission) keep their access logs.
    """

    _NOISY_PATHS = ("/api/jobs/", "/api/health")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(p in msg for p in self._NOISY_PATHS)


logging.getLogger("uvicorn.access").addFilter(_NoPollingAccessLog())


# ─── The app ────────────────────────────────────────────────────────
app = FastAPI(title="QALLM Research Pipeline", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Session state ──────────────────────────────────────────────────
# In-memory, single-process session store (documented v1 choice). Shared
# by every router via this module-level dict.
sessions: Dict[str, Dict] = {}


def get_state(sid: str) -> dict:
    state = sessions.get(sid)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    return state


# ─── Model catalog ──────────────────────────────────────────────────
MODEL_CATALOG = [
    {"id": "ollama:gemma4:e4b",         "provider": "ollama",    "model": "gemma4:e4b",        "label": "Ollama / Effective 4B (E4B) (local)"},
    {"id": "ollama:gemma3:4b",         "provider": "ollama",    "model": "gemma3:4b",        "label": "Ollama / Gemma3 4B (local)"},
    {"id": "ollama:gemma2",            "provider": "ollama",    "model": "gemma2",           "label": "Ollama / Gemma2 (local)"},
    {"id": "openai:gpt-4o-mini",      "provider": "openai",    "model": "gpt-4o-mini",      "label": "OpenAI / gpt-4o-mini"},
    {"id": "openai:gpt-5.4-mini",     "provider": "openai",    "model": "gpt-5.4-mini",     "label": "OpenAI / gpt-5.4-mini"},
    {"id": "openai:gpt-5-mini",       "provider": "openai",    "model": "gpt-5-mini",       "label": "OpenAI / gpt-5-mini"},
    {"id": "openai:gpt-5.4",          "provider": "openai",    "model": "gpt-5.4",          "label": "OpenAI / gpt-5.4"},
    {"id": "anthropic:claude-haiku-4.5", "provider": "anthropic", "model": "claude-haiku-4-5-20251001", "label": "Anthropic / Claude Haiku 4.5"},
    {"id": "anthropic:claude-sonnet-4",  "provider": "anthropic", "model": "claude-sonnet-4-20250514",  "label": "Anthropic / Claude Sonnet 4"},
]


def check_model_available(entry: dict) -> bool:
    provider = entry["provider"]
    if provider == "openai":
        return bool(settings.OPENAI_API_KEY)
    elif provider == "anthropic":
        return bool(settings.ANTHROPIC_API_KEY)
    elif provider == "ollama":
        return bool(settings.OLLAMA_BASE_URL)
    return False


def parse_model_id(model_id: str) -> tuple[str, str]:
    """Parse 'provider:model' into (llm_type, model_name).

    Falls back to auto-detection if no colon present.
    """
    if ":" in model_id and not model_id.startswith("gemma"):
        # provider:model format (but not ollama names like gemma3:4b)
        parts = model_id.split(":", 1)
        if parts[0] in ("openai", "anthropic", "ollama"):
            return parts[0], parts[1]

    for entry in MODEL_CATALOG:
        if entry["id"] == model_id:
            return entry["provider"], entry["model"]

    if model_id.startswith("gpt"):
        return "openai", model_id
    elif model_id.startswith("claude"):
        return "anthropic", model_id
    else:
        return "ollama", model_id


def model_label(model_id: str) -> str:
    for entry in MODEL_CATALOG:
        if entry["id"] == model_id:
            return entry["label"]
    return model_id
