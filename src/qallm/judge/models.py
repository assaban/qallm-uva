"""Data classes for the judge module.

These describe what the judge reads (a comparison of two profile verdicts)
and what it writes (a JudgeVerdict with structured deltas and an explanation).

The deltas are the empirical anchor for the thesis's validation story: every
LLM-judge verdict is stored alongside the numerical deltas that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from qallm.evaluation import IndicatorStatus
from qallm.profiles import QualityDimension


class JudgeOutcome(str, Enum):
    """The three verdict outcomes the judge can produce."""

    IMPROVEMENT = "improvement"
    REGRESSION = "regression"
    NO_CHANGE = "no_change"


class IndicatorChange(str, Enum):
    """How one indicator changed between parent and variant."""

    IMPROVED = "improved"
    REGRESSED = "regressed"
    UNCHANGED = "unchanged"
    INCOMPARABLE = "incomparable"  # one or both sides have no measured value


@dataclass
class IndicatorDelta:
    """The change in one indicator between parent and variant.

    Both status and measured-value changes are recorded. They can disagree:
    an indicator may improve in measured value while remaining the same
    status (e.g. both pass, but MI rose from 65 to 75). The structured form
    of this disagreement is what the thesis needs to validate model
    judgements against the raw numbers.
    """

    name: str
    evaluator: str
    parent_status: IndicatorStatus
    variant_status: IndicatorStatus
    parent_measured: float | None
    variant_measured: float | None
    comparator: str  # "ge", "le", etc., from the indicator spec
    change: IndicatorChange
    # Numeric delta: variant_measured - parent_measured if both are present.
    delta: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "evaluator": self.evaluator,
            "parent_status": self.parent_status.value,
            "variant_status": self.variant_status.value,
            "parent_measured": self.parent_measured,
            "variant_measured": self.variant_measured,
            "comparator": self.comparator,
            "change": self.change.value,
            "delta": self.delta,
        }


@dataclass
class DimensionDelta:
    """The change in one dimension (a roll-up of its indicators)."""

    dimension: QualityDimension
    parent_status: IndicatorStatus
    variant_status: IndicatorStatus
    indicator_deltas: list[IndicatorDelta] = field(default_factory=list)

    @property
    def any_regression(self) -> bool:
        return any(d.change is IndicatorChange.REGRESSED for d in self.indicator_deltas)

    @property
    def any_improvement(self) -> bool:
        return any(d.change is IndicatorChange.IMPROVED for d in self.indicator_deltas)

    @property
    def status_regressed(self) -> bool:
        """Whether the rolled-up dimension status got worse.

        Worse means moving from PASS to anything else, or from SKIPPED to
        FAIL/ERROR. SKIPPED → PASS is not a regression.
        """
        order = {
            IndicatorStatus.PASS: 0,
            IndicatorStatus.SKIPPED: 1,
            IndicatorStatus.FAIL: 2,
            IndicatorStatus.ERROR: 3,
        }
        return order[self.variant_status] > order[self.parent_status]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "parent_status": self.parent_status.value,
            "variant_status": self.variant_status.value,
            "any_regression": self.any_regression,
            "any_improvement": self.any_improvement,
            "status_regressed": self.status_regressed,
            "indicator_deltas": [d.to_dict() for d in self.indicator_deltas],
        }


@dataclass
class VerdictComparison:
    """A complete numerical comparison of two ProfileVerdicts.

    This is the structured evidence that all three judge strategies consult.
    The Strict and Lexicographic strategies derive their verdict directly
    from it; the Model strategy uses it as part of the prompt and also stores
    it for validation against the model's free-text reasoning.
    """

    dimension_deltas: list[DimensionDelta] = field(default_factory=list)

    @property
    def any_regression(self) -> bool:
        return any(d.any_regression for d in self.dimension_deltas)

    @property
    def any_improvement(self) -> bool:
        return any(d.any_improvement for d in self.dimension_deltas)

    @property
    def any_status_regression(self) -> bool:
        return any(d.status_regressed for d in self.dimension_deltas)

    def to_dict(self) -> dict[str, Any]:
        return {
            "any_regression": self.any_regression,
            "any_improvement": self.any_improvement,
            "any_status_regression": self.any_status_regression,
            "dimension_deltas": [d.to_dict() for d in self.dimension_deltas],
        }


@dataclass
class JudgeVerdict:
    """What a judge strategy returns.

    Fields are deliberately verbose: a thesis-quality artefact should be
    fully self-describing without needing to recover lost context.
    """

    outcome: JudgeOutcome
    strategy: str  # "strict", "lexicographic", "model"
    explanation: str
    comparison: VerdictComparison
    # Model strategy only: raw LLM response text (whatever the model
    # produced), preserved for thesis validation. None for rule-based.
    model_raw_response: str | None = None
    # Model strategy: which model produced this verdict.
    judge_model: str | None = None
    # True iff a Model strategy fell back to Strict after an LLM failure.
    fallback_used: bool = False
    # Optional confidence score the model self-reported (0..1). None for
    # rule-based strategies.
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "strategy": self.strategy,
            "explanation": self.explanation,
            "comparison": self.comparison.to_dict(),
            "model_raw_response": self.model_raw_response,
            "judge_model": self.judge_model,
            "fallback_used": self.fallback_used,
            "confidence": self.confidence,
        }
