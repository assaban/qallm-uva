"""Tests for the FedLLM (EGI) OpenAI-compatible provider."""

from unittest.mock import patch, MagicMock

from qallm.llm.fedllm_provider import FedLLMModel
from qallm.config import settings


def test_default_model_from_settings():
    assert FedLLMModel().name() == settings.FEDLLM_MODEL


def test_explicit_model_id_overrides_default():
    assert FedLLMModel("gpt-oss-20b").name() == "gpt-oss-20b"


def test_provider_label_is_fedllm():
    assert FedLLMModel()._provider_label() == "fedllm"


def test_is_configured_follows_fedllm_key(monkeypatch):
    monkeypatch.setattr(settings, "FEDLLM_API_KEY", None)
    assert FedLLMModel().is_configured() is False
    monkeypatch.setattr(settings, "FEDLLM_API_KEY", "sk-test")
    assert FedLLMModel().is_configured() is True


def test_is_configured_independent_of_openai_key(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-openai")
    monkeypatch.setattr(settings, "FEDLLM_API_KEY", None)
    assert FedLLMModel().is_configured() is False


def test_build_client_uses_fedllm_base_url_and_key(monkeypatch):
    monkeypatch.setattr(settings, "FEDLLM_API_KEY", "sk-fed")
    monkeypatch.setattr(settings, "FEDLLM_BASE_URL", "https://llm.ai.egi.eu/v1")
    captured = {}

    class FakeOpenAI:
        def __init__(self, api_key=None, base_url=None):
            captured["api_key"] = api_key
            captured["base_url"] = base_url

    fake_openai = MagicMock()
    fake_openai.OpenAI = FakeOpenAI
    with patch.dict("sys.modules", {"openai": fake_openai}):
        FedLLMModel()._build_client()
    assert captured["api_key"] == "sk-fed"
    assert captured["base_url"] == "https://llm.ai.egi.eu/v1"


def test_unconfigured_chat_returns_clean_error(monkeypatch):
    monkeypatch.setattr(settings, "FEDLLM_API_KEY", None)
    resp = FedLLMModel().chat("sys", "user")
    assert resp.error is not None
    assert resp.provider == "fedllm"
    assert resp.content == ""


def test_registered_in_provider_map():
    from qallm.orchestrator import LLM_PROVIDERS
    assert LLM_PROVIDERS["fedllm"] is FedLLMModel
