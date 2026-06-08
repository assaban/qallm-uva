"""Docs endpoints: serve the project's own Markdown docs as rendered HTML.

The README and the docs/ tree are a treasure for the project; this surfaces
them inside the web UI so users can read them without leaving the app. The
content is first-party and trusted, so it is rendered server-side to HTML here
and the frontend displays it directly.

Endpoints:
    GET /api/docs            -> list of available docs (id, title, path)
    GET /api/docs/{doc_id}   -> {id, title, html} for one doc

Locating the docs at runtime is the tricky part: QALLM runs three ways, from a
source checkout (docs/ beside the repo root), pip-installed into site-packages
(where __file__ is far from any repo, and docs/ may have been shipped as
package data under qallm/_docs/), and in Docker (working directory holds
README.md and, now, docs/). Rather than guess from __file__ alone, _doc_roots
yields every plausible base directory in priority order and each lookup uses
the first base that actually contains the file. This makes the endpoints work
in all three layouts and degrade gracefully (empty list / 404) when a doc is
genuinely absent.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import markdown
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()

# This file: .../qallm/api/routers/docs.py
#   parents[0] routers, [1] api, [2] qallm, [3] src (checkout) or site-packages
_THIS = Path(__file__).resolve()
_QALLM_PKG = _THIS.parents[2]            # the installed qallm/ package dir


def _doc_roots() -> list[Path]:
    """Candidate base directories that may contain README.md and docs/.

    Priority: explicit override, then packaged data shipped beside the code,
    then the process working directory (Docker WORKDIR holds README.md and
    docs/), then the source-checkout repo root inferred from __file__.
    Duplicates and non-existent paths are dropped.
    """
    candidates: list[Path] = []
    env = os.getenv("QALLM_DOCS_ROOT")
    if env:
        candidates.append(Path(env))
    # Docs shipped as package data, e.g. qallm/_docs/{README.md,docs/...}.
    candidates.append(_QALLM_PKG / "_docs")
    # Process working directory (Docker runs from the dir holding README.md).
    candidates.append(Path.cwd())
    # Source checkout: src/qallm/... -> repo root is parents[4] when present.
    if len(_THIS.parents) >= 5:
        candidates.append(_THIS.parents[4])

    seen: set[Path] = set()
    roots: list[Path] = []
    for c in candidates:
        try:
            rc = c.resolve()
        except OSError:
            continue
        if rc in seen or not rc.is_dir():
            continue
        seen.add(rc)
        roots.append(rc)
    return roots


def _resolve(rel: str) -> Path | None:
    """First existing path for a repo-relative doc, across the candidate roots."""
    for root in _doc_roots():
        p = root / rel
        if p.is_file():
            return p
    return None


# The curated set surfaced in the UI. Keys are stable ids used by the
# frontend; values are (title, path-relative-to-a-doc-root). README first.
_DOCS: dict[str, tuple[str, str]] = {
    "readme": ("Overview (README)", "README.md"),
    "workflow": ("How QALLM works", "docs/architecture/workflow-design.md"),
    "surpassing": ("Why execution beats static analysis", "docs/concepts/surpassing-static-analysers.md"),
    "running-experiments": ("Running experiments", "docs/guides/running-experiments.md"),
    "roadmap": ("Roadmap", "docs/thesis/roadmap.md"),
}

_MD_EXTENSIONS = ["fenced_code", "tables", "toc", "sane_lists"]


def _render(md_text: str) -> str:
    return markdown.markdown(md_text, extensions=_MD_EXTENSIONS)


@router.get("/api/docs")
def list_docs() -> dict:
    """List the docs available to render, in display order.

    Only docs whose file is found under some candidate root are returned, so a
    layout missing the docs tree simply shows fewer entries (README should be
    present in every layout).
    """
    items = []
    for doc_id, (title, rel) in _DOCS.items():
        if _resolve(rel) is not None:
            items.append({"id": doc_id, "title": title, "path": rel})
    if not items:
        # Surface the failure: every layout should at least find the README.
        logger.warning(
            "No docs found. Searched roots: %s",
            [str(r) for r in _doc_roots()],
        )
    return {"docs": items}


@router.get("/api/docs/{doc_id}")
def get_doc(doc_id: str) -> dict:
    """Return one doc rendered to HTML."""
    entry = _DOCS.get(doc_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown doc: {doc_id}")
    title, rel = entry
    path = _resolve(rel)
    if path is None:
        raise HTTPException(status_code=404, detail=f"Doc not found: {rel}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not read {rel}: {e}")
    return {"id": doc_id, "title": title, "html": _render(text)}
