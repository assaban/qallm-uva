"""Data models for the verification module.

These models represent the inputs, intermediate artifacts, and outputs
of the test generation and execution pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, List

from qallm.repair.repair_model import RepairedCodeUnit


@dataclass
class TestedCodeUnit:
    """The outcome of Stage 3: Verification."""
    __test__ = False  # pytest: this is a data class, not a test class
    repaired_unit: RepairedCodeUnit
    sessions: List[TestGenerationSession] = field(default_factory=list) #

    @property
    def total_bugs(self) -> int:
        """Sum of bugs found across all function sessions."""
        return sum(s.final_bugs for s in self.sessions) #[cite: 41]

    @property
    def avg_coverage(self) -> float:
        """Average coverage across all tested functions."""
        valid_covs = [s.final_coverage for s in self.sessions if s.final_coverage is not None]
        return sum(valid_covs) / len(valid_covs) if valid_covs else 0.0 #[cite: 41]

@dataclass(frozen=True)
class FunctionInfo:
    """A single extractable function from a Python source file."""

    name: str
    source: str
    docstring: str | None
    args: list[tuple[str, str | None]]  # (arg_name, annotation_or_None)
    lineno: int
    filepath: str


OracleType = Literal["crash", "property", "metamorphic"]


@dataclass
class GeneratedTest:
    """The output of a single test generation call."""

    function_name: str
    oracle: OracleType
    test_code: str
    is_valid: bool  # True if test_code compiles as Python
    generation_error: str | None = None
    model: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class TestDetail:
    """Result of a single test case within a test run."""

    __test__ = False  # prevent pytest from collecting this as a test class

    name: str
    status: Literal["passed", "failed", "error", "skipped"]
    message: str | None = None
    duration_seconds: float = 0.0


@dataclass
class ExecutionResult:
    """The output of running a generated test file."""

    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    total: int = 0
    coverage_percent: float | None = None
    coverage_branches: dict[str, float] = field(default_factory=dict)
    duration_seconds: float = 0.0
    test_details: list[TestDetail] = field(default_factory=list)
    execution_error: str | None = None
    stdout: str = ""
    stderr: str = ""

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.failed == 0 and self.errors == 0

    @property
    def validity_rate(self) -> float:
        """Proportion of tests that actually ran (not errored on collection)."""
        if self.total == 0:
            return 0.0
        return (self.total - self.errors) / self.total

    @property
    def bugs_found(self) -> int:
        """Number of tests that revealed a bug (failed, not errored)."""
        return self.failed


@dataclass
class RewardBreakdown:
    """Detailed scoring breakdown from the reward function.

    Each component contributes to the total scalar reward. This breakdown
    is stored per round for the learning curve analysis (RQ1).
    """

    bug_reward: float = 0.0  # +1.0 per bug found
    coverage_reward: float = 0.0  # +0.5 per new coverage percentage point
    validity_penalty: float = 0.0  # -0.5 per invalid/errored test
    redundancy_penalty: float = 0.0  # -0.2 per test that adds no new coverage and finds no bugs
    total: float = 0.0

    # Raw metrics used in the calculation
    bugs_found: int = 0
    coverage_gain: float = 0.0  # percentage points gained vs previous round
    valid_tests: int = 0
    invalid_tests: int = 0
    redundant_tests: int = 0


@dataclass
class RoundResult:
    """The outcome of a single round in the RL feedback loop."""

    round_number: int
    generated_test: GeneratedTest
    execution: ExecutionResult
    reward: RewardBreakdown
    cumulative_coverage: float | None = None  # best coverage seen so far
    cumulative_bugs: int = 0  # total unique bugs found so far


@dataclass
class TestGenerationSession:
    """Complete record of an RL verification run across all rounds.

    Stored as JSON for reproducibility and learning curve analysis.
    """

    __test__ = False  # pytest: this is a data class, not a test class

    function_name: str
    source_code: str
    oracle: OracleType
    model: str
    total_rounds: int
    rounds: list[RoundResult] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    @property
    def final_coverage(self) -> float | None:
        if not self.rounds:
            return None
        return self.rounds[-1].cumulative_coverage

    @property
    def final_bugs(self) -> int:
        if not self.rounds:
            return 0
        return self.rounds[-1].cumulative_bugs

    @property
    def final_pass_rate(self) -> float | None:
        """Fraction of tests that passed in the latest round.

        Returns ``None`` if there are no rounds, or if the latest round ran
        zero tests (so the ratio is undefined). Errors do not count as failed
        tests: pass_rate is ``passed / (passed + failed)``, excluding errored
        and skipped tests, because we want a clean reliability signal.
        """
        if not self.rounds:
            return None
        latest = self.rounds[-1].execution
        if latest is None:
            return None
        denom = latest.passed + latest.failed
        if denom == 0:
            return None
        return latest.passed / denom

    @property
    def learning_curve(self) -> list[float]:
        """Cumulative reward trend across rounds[cite: 28]."""
        curve = []
        cumulative = 0.0
        for r in self.rounds:
            # Defensive check: skip if reward is missing or treat as 0
            if r.reward and hasattr(r.reward, 'total'):
                cumulative += r.reward.total
            curve.append(round(cumulative, 2))
        return curve

    @property
    def reward_per_round(self) -> list[float]:
        """List of per-round reward values, for slope calculation."""
        return [round(r.reward.total, 4) for r in self.rounds]