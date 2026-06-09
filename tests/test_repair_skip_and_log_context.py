"""Tests for the zero-findings repair short-circuit and unit log context."""

import logging
from pathlib import Path
from unittest.mock import MagicMock

from qallm.analysis.analysis_model import AnalysedCodeUnit
from qallm.common.model import CodeUnit
from qallm.repair.repair_manager import RepairManager


def _analysed(findings):
    unit = CodeUnit(source_code="def f():\n    return 1\n", cell_index=0,
                    original_path=Path("example.py"))
    return AnalysedCodeUnit(code_unit=unit, findings=findings, raw_tool_results={})


def test_repair_skips_llm_when_no_findings():
    # With zero findings there is nothing to repair, so the repair agent (an
    # LLM call) must not be invoked: that was wasted budget.
    agent = MagicMock()
    analyzer = MagicMock()
    mgr = RepairManager(repair_agent=agent, analyzer=analyzer)

    result = mgr.repair_code_unit(_analysed(findings=[]))

    agent.repair.assert_not_called()
    # Identity result: source unchanged, compiles, empty diff.
    assert result.repaired_result.repaired_source == "def f():\n    return 1\n"
    assert result.repaired_result.compiles is True
    assert result.repaired_result.unified_diff == ""


def test_repair_calls_llm_when_findings_present():
    # With findings, the agent IS called (guard against over-eager skipping).
    agent = MagicMock()
    repaired = MagicMock()
    repaired.repaired_source = "def f():\n    return 2\n"
    repaired.compiles = True
    agent.repair.return_value = repaired
    mgr = RepairManager(repair_agent=agent, analyzer=MagicMock())

    mgr.repair_code_unit(_analysed(findings=[MagicMock()]))

    agent.repair.assert_called_once()


# ── unit log context ──

def test_unit_context_prefixes_log_records(caplog):
    from qallm.utils.log_context import (
        install_unit_context_filter, set_unit_context, clear_unit_context,
    )
    # caplog uses its own handler; attach the filter to it so the prefix shows.
    from qallm.utils.log_context import _FILTER_SINGLETON
    caplog.handler.addFilter(_FILTER_SINGLETON)
    install_unit_context_filter()

    log = logging.getLogger("qallm.verification.generator")
    with caplog.at_level(logging.INFO):
        set_unit_context(index=3, total=47, unit_id="datasets/lab/clean_control.py::2")
        log.info("Generating tests for add")
        clear_unit_context()
        log.info("no context here")

    messages = [r.getMessage() for r in caplog.records]
    assert any("[unit 3/47 clean_control.py::2] Generating tests for add" in m for m in messages)
    assert any(m == "no context here" for m in messages)


def test_unit_context_shortens_path():
    from qallm.utils.log_context import set_unit_context, current_unit_label, clear_unit_context
    set_unit_context(index=1, total=10, unit_id="a/b/c/deep.py::5")
    assert current_unit_label() == "[unit 1/10 deep.py::5] "
    clear_unit_context()
    assert current_unit_label() == ""


# ── repair on verification failure (Observation 2) ──

def test_runtime_failure_triggers_repair_with_zero_findings():
    from qallm.repair.repair_model import VerificationFailure
    agent = MagicMock()
    repaired = MagicMock()
    repaired.repaired_source = "def f():\n    return 2\n"
    repaired.compiles = True
    agent.repair.return_value = repaired
    mgr = RepairManager(repair_agent=agent, analyzer=MagicMock())

    vf = [VerificationFailure(
        function_name="f", failing_test="def test_f():\n    assert f() == 2",
        error_excerpt="AssertionError",
    )]
    mgr.repair_code_unit(_analysed(findings=[]), verification_failures=vf)
    # No static findings, but a runtime failure, so repair must run.
    agent.repair.assert_called_once()
    # And the request carries the verification failure.
    req = agent.repair.call_args[0][0]
    assert len(req.verification_failures) == 1
    assert req.verification_failures[0].function_name == "f"


def test_no_findings_and_no_runtime_still_skips():
    agent = MagicMock()
    mgr = RepairManager(repair_agent=agent, analyzer=MagicMock())
    mgr.repair_code_unit(_analysed(findings=[]), verification_failures=[])
    agent.repair.assert_not_called()


def test_repair_prompt_includes_failing_test():
    from qallm.repair.agents.llm_repair_agent import LLMRepairAgent
    from qallm.repair.repair_model import RepairRequest, VerificationFailure

    llm = MagicMock()
    resp = MagicMock()
    resp.content = "def f():\n    return 2\n"
    resp.model = "stub"
    llm.chat.return_value = resp
    agent = LLMRepairAgent(llm=llm, tracker=MagicMock())
    req = RepairRequest(
        file_path="x.py", original_source="def f():\n    return 1\n",
        current_findings=[],
        verification_failures=[VerificationFailure(
            "f", "def test_f():\n    assert f() == 2", "AssertionError: 1 != 2",
        )],
    )
    agent.repair(req)
    user_prompt = llm.chat.call_args[0][1]
    assert "def test_f" in user_prompt
    assert "Runtime verification failures" in user_prompt
    assert "AssertionError" in user_prompt
