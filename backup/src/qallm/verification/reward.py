"""Reward function for scoring generated test quality (T-016).

The reward function evaluates the output of the test executor and
produces a scalar score with a detailed breakdown. This score drives
the RL feedback loop (T-017): higher rewards guide the LLM toward
generating better tests in subsequent rounds.

Reward components (from the thesis proposal, Section 3.4):
    +1.0 per bug or vulnerability found (failed test)
    +0.5 per new coverage percentage point gained vs previous round
    -0.5 per invalid test (syntax error, import failure, collection error)
    -0.2 per redundant test (adds no coverage, finds no bugs)

The weights are configurable via RewardWeights.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from qallm.verification.models import ExecutionResult, RewardBreakdown

logger = logging.getLogger(__name__)


@dataclass
class RewardWeights:
    """Configurable weights for each reward component.

    Default values match the thesis proposal (Section 3.4, Figure 2).
    """

    bug_found: float = 1.0
    coverage_gain_per_point: float = 0.5
    invalid_test: float = -0.5
    redundant_test: float = -0.2


DEFAULT_WEIGHTS = RewardWeights()


def compute_reward(
    execution: ExecutionResult,
    previous_coverage: float | None = None,
    weights: RewardWeights | None = None,
) -> RewardBreakdown:
    """Score a test execution result.

    Args:
        execution: The result from running generated tests.
        previous_coverage: Branch coverage percentage from the previous round.
            None for the first round (all coverage counts as new).
        weights: Reward weights to use. Defaults to thesis proposal values.

    Returns:
        RewardBreakdown with per-component scores and a total.
    """
    w = weights or DEFAULT_WEIGHTS

    # Handle execution failure (timeout, crash before any test ran)
    if execution.execution_error:
        return RewardBreakdown(
            validity_penalty=w.invalid_test,
            total=w.invalid_test,
            invalid_tests=1,
        )

    # Handle no tests generated or collected
    if execution.total == 0:
        return RewardBreakdown(total=0.0)

    # 1. Bug discovery reward: +w per failed test
    bugs = execution.bugs_found
    bug_reward = bugs * w.bug_found

    # 2. Coverage gain reward: +w per new percentage point
    current_coverage = execution.coverage_percent or 0.0
    prev = previous_coverage or 0.0
    coverage_gain = max(0.0, current_coverage - prev)
    coverage_reward = coverage_gain * w.coverage_gain_per_point

    # 3. Validity penalty: -w per errored test (couldn't even run)
    invalid_count = execution.errors
    validity_penalty = invalid_count * w.invalid_test

    # 4. Redundancy penalty: tests that passed but added no coverage and found no bugs
    #    A test is "redundant" if: it passed, AND coverage didn't improve, AND no bugs found
    #    We estimate redundant tests as: passed tests when there's zero coverage gain and zero bugs
    if bugs == 0 and coverage_gain <= 0.0:
        redundant_count = execution.passed
    else:
        # Some tests contributed value; not all passed tests are redundant
        redundant_count = 0
    redundancy_penalty = redundant_count * w.redundant_test

    total = bug_reward + coverage_reward + validity_penalty + redundancy_penalty

    breakdown = RewardBreakdown(
        bug_reward=round(bug_reward, 4),
        coverage_reward=round(coverage_reward, 4),
        validity_penalty=round(validity_penalty, 4),
        redundancy_penalty=round(redundancy_penalty, 4),
        total=round(total, 4),
        bugs_found=bugs,
        coverage_gain=round(coverage_gain, 4),
        valid_tests=execution.total - invalid_count,
        invalid_tests=invalid_count,
        redundant_tests=redundant_count,
    )

    logger.info(
        "Reward: %.2f (bugs=%.1f, cov=%.1f, invalid=%.1f, redundant=%.1f)",
        total,
        bug_reward,
        coverage_reward,
        validity_penalty,
        redundancy_penalty,
    )

    return breakdown
