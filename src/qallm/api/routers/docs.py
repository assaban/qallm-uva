"""Docs endpoints: serve the project's own Markdown docs as rendered HTML.

The README and the docs/ tree are a treasure for the project; this surfaces
them inside the web UI so users can read them without leaving the app. The
content is first-party and trusted (it ships with the code), so it is rendered
server-side to HTML here and the frontend displays it directly.

Endpoints:
    GET /api/docs            -> list of available docs (id, title, path)
    GET /api/docs/{doc_id}   -> {id, title, html} for one doc
"""

from __future__ import annotations

import logging
from pathlib import Path

import markdown
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()

# Repo root: this file is src/qallm/api/routers/docs.py, so parents[4] is the
# project root containing README.md and docs/. In a packaged install the repo
# tree may not be present; endpoints degrade gracefully (404 / empty list).
_REPO_ROOT = Path(__file__).resolve().parents[4]

# The curated set surfaced in the UI. Keys are stable ids used by the
# frontend; values are (title, path-relative-to-repo-root). README first.
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

    Only docs whose file actually exists under the repo root are returned, so
    a packaged install without the docs tree simply shows fewer entries.
    """
    items = []
    for doc_id, (title, rel) in _DOCS.items():
        if (_REPO_ROOT / rel).is_file():
            items.append({"id": doc_id, "title": title, "path": rel})
    return {"docs": items}


@router.get("/api/docs/{doc_id}")
def get_doc(doc_id: str) -> dict:
    """Return one doc rendered to HTML."""
    entry = _DOCS.get(doc_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown doc: {doc_id}")
    title, rel = entry
    path = _REPO_ROOT / rel
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Doc not found on disk: {rel}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not read {rel}: {e}")
    return {"id": doc_id, "title": title, "html": _render(text)}
