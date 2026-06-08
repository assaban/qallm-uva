"""Tests for the in-app docs endpoints.

These exercise the real router against the real repo files (no mocks), so a
broken path mapping or a markdown-render regression is caught.
"""

from fastapi.testclient import TestClient

from qallm.api.main import app

client = TestClient(app)


def test_list_docs_includes_readme():
    r = client.get("/api/docs")
    assert r.status_code == 200
    ids = [d["id"] for d in r.json()["docs"]]
    # README must always be present and first (it is the overview).
    assert ids and ids[0] == "readme"


def test_listed_docs_all_exist_on_disk():
    # The endpoint only lists docs whose files exist, so every listed doc
    # must render without a 404.
    for d in client.get("/api/docs").json()["docs"]:
        r = client.get(f"/api/docs/{d['id']}")
        assert r.status_code == 200, d["id"]


def test_get_readme_renders_html():
    r = client.get("/api/docs/readme")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "readme"
    assert body["title"]
    # Rendered HTML, not raw Markdown: a heading tag should be present and
    # the leading Markdown '#' should not.
    assert "<h1" in body["html"]
    assert not body["html"].lstrip().startswith("#")


def test_unknown_doc_returns_404():
    r = client.get("/api/docs/does-not-exist")
    assert r.status_code == 404


def test_fenced_code_renders_as_pre():
    # The README has fenced code blocks; the fenced_code extension should
    # turn them into <pre>/<code>, which the UI styles.
    html = client.get("/api/docs/readme").json()["html"]
    assert "<pre>" in html or "<code>" in html
