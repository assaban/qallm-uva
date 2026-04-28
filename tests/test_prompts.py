"""Tests for oracle-specific prompt templates."""
import pytest
from qallm.verification.models import FunctionInfo
from qallm.verification.prompts import (
    SYSTEM_PROMPT,
    build_crash_oracle_prompt,
    build_property_oracle_prompt,
    build_metamorphic_oracle_prompt,
    build_feedback_prompt,
)
from qallm.verification.models import ExecutionResult, RewardBreakdown


@pytest.fixture
def sample_func():
    return FunctionInfo(
        name="compute_mean",
        source="def compute_mean(data):\n    return sum(data) / len(data)",
        docstring="Compute the arithmetic mean of a list of numbers.",
        args=[("data", "list[float]")],
        lineno=1,
        filepath="stats.py",
    )


def test_system_prompt_has_oracle_types():
    assert "test_" in SYSTEM_PROMPT
    assert "pytest" in SYSTEM_PROMPT


def test_crash_oracle_covers_edge_cases(sample_func):
    prompt = build_crash_oracle_prompt(sample_func)
    assert "compute_mean" in prompt
    assert "edge case" in prompt.lower() or "Empty" in prompt


def test_property_oracle_covers_invariants(sample_func):
    prompt = build_property_oracle_prompt(sample_func)
    assert "property" in prompt.lower() or "invariant" in prompt.lower()
    assert "compute_mean" in prompt


def test_metamorphic_oracle_covers_relations(sample_func):
    prompt = build_metamorphic_oracle_prompt(sample_func)
    assert "metamorphic" in prompt.lower()
    assert "compute_mean" in prompt


def test_feedback_prompt_includes_reward(sample_func):
    execution = ExecutionResult(passed=3, failed=1, total=4, coverage_percent=65.0)
    reward = RewardBreakdown(bug_reward=1.0, coverage_reward=2.5, total=3.5, bugs_found=1, coverage_gain=5.0)
    prompt = build_feedback_prompt(sample_func, "def test_x(): pass", execution, reward, round_number=2)
    assert "Round 2" in prompt
    assert "65.0%" in prompt
    assert "3.5" in prompt  # total reward
