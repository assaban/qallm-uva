"""Tests for the in-app docs endpoints.

These exercise the real router against the real repo files (no mocks), so a
broken path mapping or a markdown-render regression is caught. The
root-resolution tests cover the layouts QALLM runs in (source checkout, and a
working-directory layout standing in for Docker), which is where the original
"No docs found" bug lived.
"""

import os

from fastapi.testclient import TestClient

from qallm.api.main import app
from qallm.api.routers import docs as docs_mod

client = TestClient(app)


def test_list_docs_includes_readme():
    r = client.get("/api/docs")
    assert r.status_code == 200
    ids = [d["id"] for d in r.json()["docs"]]
    assert ids and ids[0] == "readme"


def test_listed_docs_all_exist_and_render():
    for d in client.get("/api/docs").json()["docs"]:
        r = client.get(f"/api/docs/{d['id']}")
        assert r.status_code == 200, d["id"]


def test_get_readme_renders_html():
    body = client.get("/api/docs/readme").json()
    assert body["id"] == "readme"
    assert body["title"]
    assert "<h1" in body["html"]
    assert not body["html"].lstrip().startswith("#")


def test_unknown_doc_returns_404():
    assert client.get("/api/docs/does-not-exist").status_code == 404


def test_fenced_code_renders_as_pre():
    html = client.get("/api/docs/readme").json()["html"]
    assert "<pre>" in html or "<code>" in html


# ── root resolution (the No-docs-found bug) ──

def test_doc_roots_includes_cwd():
    # The working directory must be a candidate root: this is what makes the
    # Docker layout work, where README.md and docs/ sit in WORKDIR but the
    # package is installed into site-packages far from any repo.
    roots = [str(r) for r in docs_mod._doc_roots()]
    assert str(os.getcwd()) in roots


def test_qallm_docs_root_env_takes_priority(tmp_path, monkeypatch):
    # An explicit override is honoured and comes first.
    (tmp_path / "README.md").write_text("# hi\n", encoding="utf-8")
    monkeypatch.setenv("QALLM_DOCS_ROOT", str(tmp_path))
    roots = docs_mod._doc_roots()
    assert roots[0] == tmp_path.resolve()


def test_resolve_finds_readme_via_some_root():
    # README must resolve in the test environment (source checkout).
    assert docs_mod._resolve("README.md") is not None


def test_resolve_returns_none_for_missing():
    assert docs_mod._resolve("docs/this-does-not-exist-xyz.md") is None


# ── mermaid rendering ──

def test_mermaid_block_becomes_renderable_pre():
    # ```mermaid fences must become <pre class="mermaid"> with UNescaped source,
    # which is what mermaid.js renders. Escaped source inside <code> would show
    # as text (the original bug: diagrams not displayed).
    md = "# T\n\n```mermaid\ngraph TD\n  A --> B\n```\n"
    out = docs_mod._render(md)
    assert '<pre class="mermaid">' in out
    assert "A --> B" in out          # arrow unescaped
    assert "--&gt;" not in out       # not HTML-escaped


def test_non_mermaid_code_stays_escaped_and_highlighted():
    # Ordinary fenced code must keep its language class and stay escaped.
    md = "```python\nx = 1 < 2\n```\n"
    out = docs_mod._render(md)
    assert 'class="language-python"' in out
    assert "1 &lt; 2" in out


def test_readme_mermaid_blocks_are_converted():
    # The README ships mermaid diagrams; the rendered endpoint must expose them
    # as renderable blocks, not escaped code.
    html = client.get("/api/docs/readme").json()["html"]
    if "mermaid" in html:   # README has at least one diagram
        assert '<pre class="mermaid">' in html
