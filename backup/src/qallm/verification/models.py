"""Data models for the verification module.

These models represent the inputs, intermediate artifacts, and outputs
of the test generation and execution pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


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
    def learning_curve(self) -> list[float]:
        """List of cumulative reward totals per round, for plotting."""
        cumulative = 0.0
        curve = []
        for r in self.rounds:
            cumulative += r.reward.total
            curve.append(round(cumulative, 4))
        return curve

    @property
    def reward_per_round(self) -> list[float]:
        """List of per-round reward values, for slope calculation."""
        return [round(r.reward.total, 4) for r in self.rounds]
