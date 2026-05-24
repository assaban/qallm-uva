"""Tests for separate repair-model and testgen-model support in the
orchestrator (NEW-08).

The orchestrator now accepts ``repair_*`` and ``testgen_*`` parameters
that let callers choose different LLMs for repair and test generation.
When unset, both inherit the session's default model.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from qallm.orchestrator import QALLMOrchestrator


@pytest.fixture(autouse=True)
def _mock_llm_providers():
    """Replace every LLM provider with a labelled MagicMock for predictability."""
    fake = MagicMock()
    fake.name = lambda: "default-stub"

    def _factory_for(label: str):
        def _make(model_name=None):
            m = MagicMock()
            m.name = lambda: f"{label}:{model_name or 'default'}"
            return m
        return _make

    with patch.dict(
        "qallm.orchestrator.LLM_PROVIDERS",
        {
            "ollama": _factory_for("ollama"),
            "openai": _factory_for("openai"),
            "anthropic": _factory_for("anthropic"),
        },
        clear=False,
    ):
        yield


class TestDefaultModelSharing:
    """If no separate models are specified, all three attributes are the
    same LLM instance (verified by identity, not equality)."""

    def test_repair_llm_is_default_llm_when_unset(self):
        orch = QALLMOrchestrator(
            llm_type="openai", model_name="gpt-4o-mini",
            rounds=1, judge_strategy="strict",
        )
        assert orch.repair_llm is orch.llm

    def test_testgen_llm_is_default_llm_when_unset(self):
        orch = QALLMOrchestrator(
            llm_type="openai", model_name="gpt-4o-mini",
            rounds=1, judge_strategy="strict",
        )
        assert orch.testgen_llm is orch.llm


class TestSeparateRepairModel:
    def test_repair_llm_is_distinct_instance_when_set(self):
        orch = QALLMOrchestrator(
            llm_type="openai", model_name="gpt-4o-mini",
            repair_llm_type="anthropic", repair_model_name="claude-haiku",
            rounds=1, judge_strategy="strict",
        )
        assert orch.repair_llm is not orch.llm
        assert "anthropic:claude-haiku" in orch.repair_llm.name()

    def test_repair_agent_uses_separate_llm(self):
        orch = QALLMOrchestrator(
            llm_type="openai", model_name="gpt-4o-mini",
            repair_llm_type="ollama", repair_model_name="gemma3:4b",
            rounds=1, judge_strategy="strict",
        )
        # The LLMRepairAgent inside the RepairManager holds the repair LLM.
        agent_llm = orch.repair_manager.repair_agent.llm
        assert agent_llm is orch.repair_llm

    def test_repair_model_name_alone_is_enough(self):
        # If only model_name is given (not type), reuse the default's type.
        orch = QALLMOrchestrator(
            llm_type="openai", model_name="gpt-4o-mini",
            repair_model_name="gpt-5-mini",
            rounds=1, judge_strategy="strict",
        )
        assert orch.repair_llm is not orch.llm
        assert "openai:gpt-5-mini" in orch.repair_llm.name()


class TestSeparateTestgenModel:
    def test_testgen_llm_is_distinct_when_set(self):
        orch = QALLMOrchestrator(
            llm_type="openai", model_name="gpt-4o-mini",
            testgen_llm_type="ollama", testgen_model_name="gemma3:4b",
            rounds=1, judge_strategy="strict",
        )
        assert orch.testgen_llm is not orch.llm
        assert "ollama:gemma3:4b" in orch.testgen_llm.name()

    def test_verification_manager_uses_testgen_llm(self):
        orch = QALLMOrchestrator(
            llm_type="openai", model_name="gpt-4o-mini",
            testgen_llm_type="anthropic", testgen_model_name="claude-haiku",
            rounds=1, judge_strategy="strict",
        )
        # The VerificationManager's TestGenerator holds the testgen LLM.
        vm_generator = orch.verification_manager.generator
        # The TestGenerator's llm attribute (look up via .llm or .generator)
        assert hasattr(vm_generator, "llm")
        assert vm_generator.llm is orch.testgen_llm


class TestBothSeparate:
    def test_repair_and_testgen_can_differ_from_default_and_each_other(self):
        orch = QALLMOrchestrator(
            llm_type="openai", model_name="gpt-4o-mini",
            repair_llm_type="anthropic", repair_model_name="claude-sonnet",
            testgen_llm_type="ollama", testgen_model_name="gemma3:4b",
            rounds=1, judge_strategy="strict",
        )
        # Three distinct instances.
        assert orch.llm is not orch.repair_llm
        assert orch.llm is not orch.testgen_llm
        assert orch.repair_llm is not orch.testgen_llm
        assert "anthropic" in orch.repair_llm.name()
        assert "ollama" in orch.testgen_llm.name()


class TestSummaryReportsBothModels:
    """The summary dict must surface repair_model and testgen_model so the
    UI can show what was actually used for each subsystem."""

    def test_summary_includes_repair_and_testgen_model_labels(self):
        orch = QALLMOrchestrator(
            llm_type="openai", model_name="gpt-4o-mini",
            repair_llm_type="anthropic", repair_model_name="claude-haiku",
            testgen_llm_type="ollama", testgen_model_name="gemma3:4b",
            rounds=1, judge_strategy="strict",
        )
        # Call the internal builder directly with empty inputs.
        summary = orch._build_summary(
            source_path="x.py",
            units=[],
            sessions_data=[],
        )
        assert "anthropic:claude-haiku" in summary["repair_model"]
        assert "ollama:gemma3:4b" in summary["testgen_model"]


class TestStageCoercion:
    """Regression: the API sends stage as a plain string ("implementation").

    The orchestrator must coerce it to a LifecycleStage before stashing
    so later code (e.g. summary building) that calls ``self.stage.value``
    doesn't crash with AttributeError on 'str'.
    """

    def test_stage_string_is_coerced_to_enum(self):
        from qallm.analysis.normalizer import LifecycleStage
        orch = QALLMOrchestrator(
            stage="implementation",
            llm_type="openai", model_name="gpt-4o-mini",
            rounds=1, judge_strategy="strict",
        )
        assert isinstance(orch.stage, LifecycleStage)
        assert orch.stage is LifecycleStage.IMPLEMENTATION

    def test_stage_enum_is_kept_as_is(self):
        from qallm.analysis.normalizer import LifecycleStage
        orch = QALLMOrchestrator(
            stage=LifecycleStage.PUBLICATION,
            llm_type="openai", model_name="gpt-4o-mini",
            rounds=1, judge_strategy="strict",
        )
        assert orch.stage is LifecycleStage.PUBLICATION

    def test_build_summary_works_after_string_stage(self):
        """The original crash: build_summary called .value on a string."""
        orch = QALLMOrchestrator(
            stage="implementation",
            llm_type="openai", model_name="gpt-4o-mini",
            rounds=1, judge_strategy="strict",
        )
        # If stage coercion failed, this raises AttributeError on .value.
        summary = orch._build_summary(source_path="x.py", units=[], sessions_data=[])
        assert summary["lifecycle_stage"] == "implementation"

    def test_unknown_stage_string_raises_clearly(self):
        with pytest.raises(ValueError):
            QALLMOrchestrator(
                stage="not_a_real_stage",
                llm_type="openai", model_name="gpt-4o-mini",
                rounds=1, judge_strategy="strict",
            )


class TestRunIdPlumbing:
    """Regression: the orchestrator must respect a caller-supplied run_id.

    The previous design captured ``datetime.now()`` inside ``__init__``,
    which meant a re-constructed orchestrator silently produced a new
    output folder. Callers now pass an explicit ``run_id`` (e.g. the
    session UUID) to pin the directory across the entire session.
    """

    def test_default_run_id_uses_timestamp(self):
        # Backwards compat: no run_id given -> timestamp-based.
        orch = QALLMOrchestrator(
            llm_type="openai", model_name="gpt-4o-mini",
            rounds=1, judge_strategy="strict",
        )
        # run_id has the YYYYMMDD_HHMMSS shape.
        assert orch.reporter.run_id.count("_") >= 1
        assert len(orch.reporter.run_id) >= 13  # at least YYYYMMDD_HHMMSS

    def test_explicit_run_id_used_verbatim(self):
        orch = QALLMOrchestrator(
            llm_type="openai", model_name="gpt-4o-mini",
            rounds=1, judge_strategy="strict",
            run_id="test_session_42",
        )
        assert orch.reporter.run_id == "test_session_42"
        assert orch.reporter.report_dir.name == "test_session_42"

    def test_two_orchestrators_with_same_run_id_share_directory(self):
        # The actual bug-fix scenario: even if two orchestrators are
        # built (e.g. server restart, second upload), supplying the same
        # run_id pins both to the same on-disk directory.
        orch1 = QALLMOrchestrator(
            llm_type="openai", model_name="gpt-4o-mini",
            rounds=1, judge_strategy="strict",
            run_id="shared_id",
        )
        orch2 = QALLMOrchestrator(
            llm_type="openai", model_name="gpt-4o-mini",
            rounds=1, judge_strategy="strict",
            run_id="shared_id",
        )
        assert orch1.reporter.report_dir == orch2.reporter.report_dir

    def test_explicit_reporter_takes_precedence_over_run_id(self):
        # If a caller passes a pre-built reporter, the orchestrator uses
        # it as-is and ignores any run_id argument.
        from qallm.utils.reporter import QualityReporter
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            reporter = QualityReporter(base_dir=td, run_id="injected")
            orch = QALLMOrchestrator(
                llm_type="openai", model_name="gpt-4o-mini",
                rounds=1, judge_strategy="strict",
                run_id="ignored_when_reporter_supplied",
                reporter=reporter,
            )
            assert orch.reporter is reporter
            assert orch.reporter.run_id == "injected"
