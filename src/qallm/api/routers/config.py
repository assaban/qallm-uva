"""API router: config endpoints.

Split from the former monolithic api/main.py. Shares the app's session
store and helpers via qallm.api.core. Behaviour is unchanged; only the
file boundary moved.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter

from qallm.api.core import (
    MODEL_CATALOG,
    check_model_available,
    get_state,
)
from qallm.orchestrator import LLM_PROVIDERS

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/llm/providers")
async def get_providers():
    return {"configured": list(LLM_PROVIDERS.keys())}


@router.get("/api/verification/strategies")
async def get_strategies():
    return {"configured": ["feedback", "oneshot", "hypothesis"]}


@router.get("/api/verification/models")
async def get_models():
    """Returns model catalog with availability status for the frontend dropdown."""
    result = []
    for entry in MODEL_CATALOG:
        available = check_model_available(entry)
        result.append({
            "id": entry["id"],
            "label": entry["label"],
            "provider": entry["provider"],
            "available": available,
        })
    return {"models": result}


@router.get("/api/sample-data")
async def get_sample_data():
    """Return bundled sample code so users can try the pipeline instantly.

    Each sample is a small module of research-style functions that pass
    static analysis but contain runtime logic bugs, demonstrating the
    verification gap. The frontend submits the chosen sample's content
    through the normal upload flow, so it runs the same path as a real
    upload.
    """

    import qallm
    sample_dir = os.path.join(os.path.dirname(qallm.__file__), "sample_data")
    samples = []
    descriptions = {
        "buggy_research_code.py": (
            "Five functions that look clean to Bandit and Radon but each "
            "hides a runtime logic bug (off-by-one, aliasing, wrong "
            "normalisation, a guard that misses zero, a reversed sort). "
            "Ideal for showing what execution-based verification catches "
            "that static analysis misses."
        ),
    }
    try:
        for name in sorted(os.listdir(sample_dir)):
            if not name.endswith(".py") or name == "__init__.py":
                continue
            path = os.path.join(sample_dir, name)
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
            samples.append({
                "name": name,
                "description": descriptions.get(name, ""),
                "content": content,
                "lines": content.count("\n") + 1,
            })
    except OSError:
        pass
    return {"samples": samples}


@router.get("/api/quality-profiles")
async def get_quality_profiles():
    """List selectable quality models (profiles) with explanations.

    Powers the pipeline-start selector. Each profile maps to a quality
    framework; QALLM evaluates the named indicators per dimension. Only
    profiles actually implemented are marked available; planned framework
    profiles are listed so the roadmap is visible in the UI.
    """
    from qallm.profiles import _BUILT_IN

    FRAMEWORK = {
        "implementation_default": "EVERSE Research Software Quality",
        "fair4rs_publication": "FAIR for Research Software (FAIR4RS)",
        "iso25010_base": "ISO/IEC 25010:2023",
    }
    FRIENDLY = {
        "implementation_default": "EVERSE (implementation stage)",
        "fair4rs_publication": "FAIR4RS (publication stage)",
        "iso25010_base": "ISO/IEC 25010 (general software)",
    }
    EXPLAIN = {
        "implementation_default": (
            "The EVERSE Research Software Quality framework, the v1 "
            "demonstrator. Evaluates Maintainability, Security, Reliability, "
            "Reproducibility, and FAIRness using static tools plus QALLM's "
            "execution-based verification. Thresholds are tuned for the "
            "implementation stage of the software lifecycle."
        ),
        "iso25010_base": (
            "The ISO/IEC 25010:2023 product quality model as a "
            "general-software base profile. All nine characteristics are "
            "declared. Security and Maintainability are measured statically; "
            "Functional Suitability is measured by QALLM's execution-based "
            "verification (the characteristic static tools cannot assess); "
            "the remaining characteristics are declared but not assessed in "
            "v1. EVERSE is this model plus FAIRness and Sustainability."
        ),
    }

    profiles = []
    for pid, profile in _BUILT_IN.items():
        profiles.append({
            "id": pid,
            "name": FRIENDLY.get(pid, pid),
            "framework": FRAMEWORK.get(pid, "Custom"),
            "description": EXPLAIN.get(pid, profile.description),
            "available": True,
            "dimensions": [
                {"name": d.dimension.value,
                 "indicators": [i.name for i in d.indicators]}
                for d in profile.dimensions
            ],
        })

    # All built-in profiles are now real and available; the roadmap list is
    # empty. SonarQube-backed indicators are a future enhancement to the
    # iso25010_base profile, not a separate profile.
    roadmap: list = []

    return {"profiles": profiles + roadmap, "default": "implementation_default"}


@router.get("/api/analysis/tools")
async def get_analysis_tools():
    return {"tools": ["bandit", "radon", "ruff", "trufflehog"]}


@router.get("/api/session/{session_id}/config")
async def get_session_config(session_id: str):
    """Returns the locked-in session configuration (model, strategy, oracle)."""
    state = get_state(session_id)
    return {"config": state.get("config", {})}


