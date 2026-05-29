"""Regression test: /favicon.ico must not 404 (known issue, now fixed)."""
from fastapi.testclient import TestClient

from qallm.api.main import app

client = TestClient(app)


def test_favicon_ico_not_404():
    r = client.get("/favicon.ico")
    assert r.status_code in (200, 204)
    if r.status_code == 200:
        assert r.headers["content-type"] == "image/svg+xml"


def test_favicon_svg_served():
    r = client.get("/favicon.svg")
    assert r.status_code in (200, 204)
