"""The orchestrator's reporter dir is configurable, so experiment runs write
their per-session artefacts away from the Web-UI session directory."""

from qallm.config import settings
from qallm.orchestrator import QALLMOrchestrator


def test_reporter_dir_defaults_to_web_ui_sessions_dir():
    orch = QALLMOrchestrator(strategy="oneshot", llm_type="fedllm", rounds=1)
    assert settings.QALLM_SESSIONS_DIR in str(orch.reporter.report_dir)


def test_explicit_reporter_dir_is_honoured(tmp_path):
    target = str(tmp_path / "experiment_artefacts")
    orch = QALLMOrchestrator(
        strategy="oneshot", llm_type="fedllm", rounds=1, reporter_dir=target,
    )
    assert str(orch.reporter.report_dir).startswith(target)


def test_web_ui_and_experiment_dirs_differ_by_default():
    # The two configured directories are distinct, so a large experiment run
    # cannot bloat the Web-UI session library directory.
    assert settings.QALLM_SESSIONS_DIR != settings.QALLM_EXPERIMENT_REPORTER_DIR
