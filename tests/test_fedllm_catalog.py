"""FedLLM appears in the web UI model catalog and availability is correct."""

from qallm.api.core import MODEL_CATALOG, check_model_available, parse_model_id
from qallm.config import settings


def test_fedllm_in_catalog():
    providers = {e["provider"] for e in MODEL_CATALOG}
    assert "fedllm" in providers
    fed = [e for e in MODEL_CATALOG if e["provider"] == "fedllm"]
    assert any(e["model"] == "gpt-oss-120b" for e in fed)


def test_fedllm_availability_follows_key(monkeypatch):
    entry = {"provider": "fedllm"}
    monkeypatch.setattr(settings, "FEDLLM_API_KEY", None)
    assert check_model_available(entry) is False
    monkeypatch.setattr(settings, "FEDLLM_API_KEY", "sk-fed")
    assert check_model_available(entry) is True


def test_parse_fedllm_model_id():
    assert parse_model_id("fedllm:gpt-oss-120b") == ("fedllm", "gpt-oss-120b")


def test_models_endpoint_lists_fedllm(monkeypatch):
    monkeypatch.setattr(settings, "FEDLLM_API_KEY", "sk-fed")
    from fastapi.testclient import TestClient
    from qallm.api.main import app
    client = TestClient(app)
    res = client.get("/api/verification/models")
    assert res.status_code == 200
    models = res.json()["models"]
    fed = [m for m in models if m["provider"] == "fedllm"]
    assert fed, "FedLLM models should be listed"
    assert all(m["available"] for m in fed), "should be available when key is set"
