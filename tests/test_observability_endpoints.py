"""Tests for the observability and selector endpoints."""
from fastapi.testclient import TestClient

from qallm.api.main import app

client = TestClient(app)


def test_sample_data_returns_bundled_module():
    r = client.get("/api/sample-data")
    assert r.status_code == 200
    samples = r.json()["samples"]
    assert len(samples) >= 1
    s = samples[0]
    assert s["name"].endswith(".py")
    assert "def " in s["content"]
    assert s["lines"] > 0


def test_quality_profiles_lists_default_and_dimensions():
    r = client.get("/api/quality-profiles")
    assert r.status_code == 200
    body = r.json()
    assert body["default"] == "implementation_default"
    impl = [p for p in body["profiles"] if p["id"] == "implementation_default"][0]
    assert impl["available"] is True
    dims = [d["name"] for d in impl["dimensions"]]
    # The five EVERSE dimensions QALLM implements.
    for expected in ("Maintainability", "Security", "Reliability",
                     "Reproducibility", "FAIRness"):
        assert expected in dims


def test_quality_profiles_all_available_no_roadmap():
    r = client.get("/api/quality-profiles")
    body = r.json()
    # All three built-in profiles are now real and available; the roadmap
    # is empty. ISO/IEC 25010 graduated from roadmap stub to a real profile.
    unavailable = [p for p in body["profiles"] if not p["available"]]
    assert unavailable == []
    available_ids = {p["id"] for p in body["profiles"] if p["available"]}
    assert {"implementation_default", "fair4rs_publication", "iso25010_base"} <= available_ids


def test_improvement_endpoint_handles_no_run():
    # A session id with no run artefacts should report unavailable, not 500.
    # Use a clearly-nonexistent session: the endpoint reads report_dir from
    # session state, which will be missing.
    r = client.get("/api/session/does-not-exist/improvement")
    # Either 404 (no such session) or 200 with available False is acceptable;
    # both are graceful. Assert it does not 500.
    assert r.status_code in (200, 404)


def test_quality_profiles_includes_two_available_real_profiles():
    r = client.get("/api/quality-profiles")
    body = r.json()
    available = {p["id"] for p in body["profiles"] if p["available"]}
    # EVERSE and FAIR4RS are both real, runnable profiles now.
    assert "implementation_default" in available
    assert "fair4rs_publication" in available
