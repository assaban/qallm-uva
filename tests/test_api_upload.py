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


class TestReanalyseUsesRepairedSource:
    """Regression: the /api/analyse endpoint must analyse the repaired
    source on Step 4 (re-analyse), not re-analyse the original code.

    Without this, repair appears to never improve quality because the
    re-analyse findings are always identical to the pre-repair findings.
    """

    def test_first_analyse_uses_original_source(self, client, monkeypatch):
        # Upload + first analysis: no repair has happened yet, so analyse
        # operates on the original source (the file's actual content).
        from unittest.mock import MagicMock
        from qallm.api.main import sessions

        # Patch the analysis_manager to record which source code it sees.
        seen_sources = []

        def fake_analyse(unit):
            seen_sources.append(unit.source_code)
            result = MagicMock()
            result.findings = []
            return result

        upload = _upload_with(client, model="openai:gpt-4o-mini")
        assert upload.status_code == 200
        sid = upload.json()["session_id"]

        orch = sessions[sid]["orchestrator"]
        monkeypatch.setattr(
            orch.analysis_manager, "analyse_code_unit", fake_analyse,
        )

        client.post("/api/analyse", json={
            "session_id": sid,
            "selected_files": [sessions[sid]["units"][0].original_path.name],
            "selected_tools": [],
        })

        assert len(seen_sources) == 1
        original = sessions[sid]["units"][0].source_code
        assert seen_sources[0] == original, (
            "First analyse must see the original source."
        )

    def test_reanalyse_after_repair_uses_repaired_source(self, client, monkeypatch):
        # The bug regression: after repair stashes a repaired variant,
        # a second call to /api/analyse must analyse the repaired source,
        # not the original.
        from unittest.mock import MagicMock
        from qallm.api.main import sessions
        from qallm.repair.repair_model import RepairedCodeUnit, RepairResult
        from qallm.analysis.analysis_model import AnalysedCodeUnit

        seen_sources = []

        def fake_analyse(unit):
            seen_sources.append(unit.source_code)
            result = MagicMock()
            result.findings = []
            return result

        upload = _upload_with(client, model="openai:gpt-4o-mini")
        sid = upload.json()["session_id"]
        orch = sessions[sid]["orchestrator"]
        monkeypatch.setattr(
            orch.analysis_manager, "analyse_code_unit", fake_analyse,
        )

        name = sessions[sid]["units"][0].original_path.name
        original_unit = sessions[sid]["units"][0]
        original_source = original_unit.source_code

        # Stash a fake repaired variant directly into session state, as
        # /api/repair would do.
        repaired_source = "# repaired\n" + original_source + "\n# end repair\n"
        repair_result = RepairResult(
            file_path=str(original_unit.original_path),
            repaired_source=repaired_source,
            explanation="fake repair for test",
            compiles=True,
        )
        analysed = AnalysedCodeUnit(code_unit=original_unit)
        repaired_unit = RepairedCodeUnit(
            analysis_result=analysed,
            repaired_result=repair_result,
        )
        sessions[sid]["repaired_units"][name] = repaired_unit

        # Now call /api/analyse a second time: this is "re-analyse."
        client.post("/api/analyse", json={
            "session_id": sid,
            "selected_files": [name],
            "selected_tools": [],
        })

        assert len(seen_sources) == 1
        assert seen_sources[0] == repaired_source, (
            "Re-analyse must see the repaired source, not the original."
        )
        assert seen_sources[0] != original_source, (
            "Sanity: the repaired source should be different from the "
            "original for this test to be meaningful."
        )

    def test_failed_repair_falls_back_to_original_source(self, client, monkeypatch):
        # If repair produced a non-compiling output, we don't trust it;
        # analyse falls back to the original.
        from unittest.mock import MagicMock
        from qallm.api.main import sessions
        from qallm.repair.repair_model import RepairedCodeUnit, RepairResult
        from qallm.analysis.analysis_model import AnalysedCodeUnit

        seen_sources = []

        def fake_analyse(unit):
            seen_sources.append(unit.source_code)
            result = MagicMock()
            result.findings = []
            return result

        upload = _upload_with(client, model="openai:gpt-4o-mini")
        sid = upload.json()["session_id"]
        orch = sessions[sid]["orchestrator"]
        monkeypatch.setattr(
            orch.analysis_manager, "analyse_code_unit", fake_analyse,
        )

        name = sessions[sid]["units"][0].original_path.name
        original_unit = sessions[sid]["units"][0]
        original_source = original_unit.source_code

        # Stash a *broken* repair: compiles=False.
        repair_result = RepairResult(
            file_path=str(original_unit.original_path),
            repaired_source="!!!! syntax error",
            explanation="broken repair",
            compiles=False,
        )
        analysed = AnalysedCodeUnit(code_unit=original_unit)
        repaired_unit = RepairedCodeUnit(
            analysis_result=analysed,
            repaired_result=repair_result,
        )
        sessions[sid]["repaired_units"][name] = repaired_unit

        client.post("/api/analyse", json={
            "session_id": sid,
            "selected_files": [name],
            "selected_tools": [],
        })

        assert seen_sources[0] == original_source, (
            "When the repaired source doesn't compile, analyse must fall "
            "back to the original to avoid analysing broken code."
        )
