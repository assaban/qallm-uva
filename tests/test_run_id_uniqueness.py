"""Run IDs must be unique even when orchestrators start in the same second.

Regression: parallel --workers runs created several orchestrators within one
second; a bare %Y%m%d_%H%M%S run_id collided, so workers shared one report
directory and cross-contaminated each other's metrics (all sessions showed
identical numbers). The fallback run_id now carries a uuid suffix.
"""

from unittest.mock import patch
from qallm.orchestrator import QALLMOrchestrator


def _make(**kw):
    # Build with rule-based judge and a stub LLM type that does not connect;
    # we only need __init__ to set up the reporter run_id.
    return QALLMOrchestrator(
        strategy="feedback", llm_type="fedllm", rounds=1,
        judge_strategy="lexicographic", **kw,
    )


def test_fallback_run_id_is_unique_within_a_second():
    fixed = "20260610_134007"
    ids = set()
    # Freeze the timestamp so all four share the same second; the uuid suffix
    # must still make them unique.
    with patch("qallm.orchestrator.datetime") as dt:
        dt.now.return_value.strftime.return_value = fixed
        for _ in range(4):
            orch = _make()
            ids.add(orch.reporter.run_id)
    assert len(ids) == 4, f"run_ids collided: {ids}"
    assert all(rid.startswith(fixed + "_") for rid in ids)


def test_explicit_run_id_is_respected():
    orch = _make(run_id="my-fixed-run")
    assert orch.reporter.run_id == "my-fixed-run"
