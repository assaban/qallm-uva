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
