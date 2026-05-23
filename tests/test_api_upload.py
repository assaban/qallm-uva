"""Tests for the web API upload endpoint configuration plumbing (NEW-08).

The upload endpoint accepts the full v1 configuration surface; this file
verifies each new field is forwarded to the orchestrator and recorded in
the session's config dict for later read-back.
"""

from __future__ import annotations

import io
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _stub_llm_providers():
    """LLM providers are stubbed for the entire test module to avoid any
    real API calls during upload (which constructs the orchestrator).

    Patches the LLM_PROVIDERS dict so any of openai/anthropic/ollama
    resolves to a labelled mock factory.
    """

    def _factory(label: str):
        def _make(model_name=None):
            m = MagicMock()
            m.name = lambda mn=model_name, lb=label: f"{lb}:{mn or 'default'}"
            return m
        return _make

    with patch.dict(
        "qallm.orchestrator.LLM_PROVIDERS",
        {
            "ollama": _factory("ollama"),
            "openai": _factory("openai"),
            "anthropic": _factory("anthropic"),
        },
        clear=False,
    ):
        yield


@pytest.fixture
def client():
    from qallm.api.main import app, sessions
    sessions.clear()
    return TestClient(app)


def _make_upload(content: bytes = b"def f(): pass\n", name: str = "demo.py"):
    return {"archives": (name, io.BytesIO(content), "text/plain")}


def _upload_with(client, **form_overrides):
    """Helper: build a multipart upload with the supplied form fields."""
    files = _make_upload()
    return client.post("/api/session/upload", files=files, data=form_overrides)


class TestBasicUpload:
    def test_minimum_upload_succeeds(self, client):
        resp = _upload_with(client)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "session_id" in body
        assert "config" in body

    def test_session_config_contains_v1_defaults(self, client):
        resp = _upload_with(client)
        config = resp.json()["config"]
        # Defaults that the upload endpoint now sets.
        assert config["judge_strategy"] == "lexicographic"
        assert config["test_stability"] == "frozen"
        assert config["generation_policy"] == "grow"


class TestAdvancedSettingsPlumbing:
    def test_judge_strategy_round_trips(self, client):
        resp = _upload_with(client, judge_strategy="strict")
        assert resp.status_code == 200
        assert resp.json()["config"]["judge_strategy"] == "strict"

    def test_test_stability_round_trips(self, client):
        resp = _upload_with(client, test_stability="per_round")
        assert resp.status_code == 200
        assert resp.json()["config"]["test_stability"] == "per_round"

    def test_generation_policy_round_trips(self, client):
        resp = _upload_with(client, generation_policy="replay_only")
        assert resp.status_code == 200
        assert resp.json()["config"]["generation_policy"] == "replay_only"

    def test_budget_caps_round_trip(self, client):
        resp = _upload_with(
            client,
            max_tokens=10000,
            max_seconds=300.0,
            max_round_seconds=60.0,
            max_cost_usd=0.50,
        )
        assert resp.status_code == 200
        cfg = resp.json()["config"]
        assert cfg["max_tokens"] == 10000
        assert cfg["max_seconds"] == 300.0
        assert cfg["max_round_seconds"] == 60.0
        assert cfg["max_cost_usd"] == 0.50

    def test_budget_caps_default_to_none(self, client):
        resp = _upload_with(client)
        cfg = resp.json()["config"]
        assert cfg["max_tokens"] is None
        assert cfg["max_seconds"] is None
        assert cfg["max_round_seconds"] is None
        assert cfg["max_cost_usd"] is None


class TestSeparateModels:
    def test_separate_models_recorded_independently(self, client):
        resp = _upload_with(
            client,
            model="openai:gpt-4o-mini",
            repair_model="anthropic:claude-haiku-4.5",
            testgen_model="ollama:gemma3:4b",
        )
        assert resp.status_code == 200
        cfg = resp.json()["config"]
        assert cfg["model_id"] == "openai:gpt-4o-mini"
        assert cfg["repair_model_id"] == "anthropic:claude-haiku-4.5"
        assert cfg["testgen_model_id"] == "ollama:gemma3:4b"

    def test_unset_separate_models_inherit_default(self, client):
        resp = _upload_with(client, model="openai:gpt-4o-mini")
        cfg = resp.json()["config"]
        # Both subsystems fall back to the default model id.
        assert cfg["repair_model_id"] == "openai:gpt-4o-mini"
        assert cfg["testgen_model_id"] == "openai:gpt-4o-mini"


class TestConfigEndpointReadback:
    def test_get_config_returns_full_config(self, client):
        resp = _upload_with(
            client,
            judge_strategy="model",
            test_stability="per_round",
            max_cost_usd=1.0,
            repair_model="anthropic:claude-sonnet-4",
        )
        sid = resp.json()["session_id"]

        cfg_resp = client.get(f"/api/session/{sid}/config")
        assert cfg_resp.status_code == 200
        cfg = cfg_resp.json()["config"]
        assert cfg["judge_strategy"] == "model"
        assert cfg["test_stability"] == "per_round"
        assert cfg["max_cost_usd"] == 1.0
        assert cfg["repair_model_id"] == "anthropic:claude-sonnet-4"
