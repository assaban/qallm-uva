"""Tests for qallm.judge.

Coverage:

  * comparator: indicator classification (IMPROVED, REGRESSED, UNCHANGED,
    INCOMPARABLE) across all relevant combinations of status and measured
    value.
  * comparator: dimension-level rollup, including asymmetric profiles.
  * StrictJudge: regression wins over improvement; neutral comparisons
    yield NO_CHANGE.
  * LexicographicJudge: priority ordering; high-priority regression
    blocks lower-priority improvement.
  * ModelJudge: structured JSON path, fenced-JSON path, parse-failure
    fallback, LLM-error fallback.
  * build_judge: factory dispatch and the ModelJudge-needs-llm error.

ModelJudge tests use a stub LLM; no real API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from qallm.evaluation import (
    DimensionResult,
    IndicatorResult,
    IndicatorStatus,
    ProfileVerdict,
)
from qallm.judge import (
    JudgeOutcome,
    JudgeStrategy,
    LexicographicJudge,
    ModelJudge,
    StrictJudge,
    build_judge,
)
from qallm.judge.comparator import compare_verdicts
from qallm.judge.models import IndicatorChange
from qallm.llm.base import LLMResponse
from qallm.profiles import QualityDimension


# ---------- helpers ----------


def _indicator(
    name: str,
    status: IndicatorStatus,
    measured: float | None,
    comparator: str = "ge",
    threshold: float = 0.0,
    evaluator: str = "stub.eval",
) -> IndicatorResult:
    return IndicatorResult(
        name=name,
        evaluator=evaluator,
        threshold=threshold,
        comparator=comparator,
        measured=measured,
        status=status,
    )


def _dim(
    dimension: QualityDimension, *indicators: IndicatorResult
) -> DimensionResult:
    return DimensionResult(dimension=dimension, indicators=list(indicators))


def _verdict(*dims: DimensionResult, profile_id: str = "stub") -> ProfileVerdict:
    return ProfileVerdict(profile_id=profile_id, dimensions=list(dims))


# ---------- comparator: indicator classification ----------


class TestIndicatorClassification:
    """The 16 combinations are too many; cover the meaningful ones."""

    def test_both_pass_higher_measured_is_improvement_for_ge(self):
        parent = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 60.0, comparator="ge")))
        variant = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 75.0, comparator="ge")))
        comp = compare_verdicts(parent, variant)
        d = comp.dimension_deltas[0].indicator_deltas[0]
        assert d.change is IndicatorChange.IMPROVED
        assert d.delta == 15.0

    def test_both_pass_lower_measured_is_regression_for_ge(self):
        parent = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 75.0, comparator="ge")))
        variant = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 60.0, comparator="ge")))
        comp = compare_verdicts(parent, variant)
        d = comp.dimension_deltas[0].indicator_deltas[0]
        assert d.change is IndicatorChange.REGRESSED
        assert d.delta == -15.0

    def test_le_comparator_inverts_direction(self):
        # Lower is better for LE comparators (bandit count, complexity).
        parent = _verdict(_dim(QualityDimension.SECURITY,
            _indicator("bandit", IndicatorStatus.PASS, 5.0, comparator="le")))
        variant = _verdict(_dim(QualityDimension.SECURITY,
            _indicator("bandit", IndicatorStatus.PASS, 2.0, comparator="le")))
        comp = compare_verdicts(parent, variant)
        d = comp.dimension_deltas[0].indicator_deltas[0]
        # Lower means improvement under LE; delta is variant - parent = -3.
        assert d.change is IndicatorChange.IMPROVED
        assert d.delta == -3.0

    def test_same_measured_is_unchanged(self):
        parent = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 70.0)))
        variant = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 70.0)))
        comp = compare_verdicts(parent, variant)
        d = comp.dimension_deltas[0].indicator_deltas[0]
        assert d.change is IndicatorChange.UNCHANGED

    def test_status_only_when_no_measured(self):
        # No measured values, but statuses differ: should fall back to status.
        parent = _verdict(_dim(QualityDimension.RELIABILITY,
            _indicator("x", IndicatorStatus.FAIL, None)))
        variant = _verdict(_dim(QualityDimension.RELIABILITY,
            _indicator("x", IndicatorStatus.PASS, None)))
        comp = compare_verdicts(parent, variant)
        d = comp.dimension_deltas[0].indicator_deltas[0]
        assert d.change is IndicatorChange.IMPROVED

    def test_error_makes_indicator_incomparable(self):
        parent = _verdict(_dim(QualityDimension.RELIABILITY,
            _indicator("x", IndicatorStatus.PASS, 1.0)))
        variant = _verdict(_dim(QualityDimension.RELIABILITY,
            _indicator("x", IndicatorStatus.ERROR, None)))
        comp = compare_verdicts(parent, variant)
        d = comp.dimension_deltas[0].indicator_deltas[0]
        assert d.change is IndicatorChange.INCOMPARABLE

    def test_skipped_on_both_is_unchanged(self):
        parent = _verdict(_dim(QualityDimension.REPRODUCIBILITY,
            _indicator("env", IndicatorStatus.SKIPPED, None)))
        variant = _verdict(_dim(QualityDimension.REPRODUCIBILITY,
            _indicator("env", IndicatorStatus.SKIPPED, None)))
        comp = compare_verdicts(parent, variant)
        d = comp.dimension_deltas[0].indicator_deltas[0]
        assert d.change is IndicatorChange.UNCHANGED

    def test_skipped_on_one_side_is_incomparable(self):
        parent = _verdict(_dim(QualityDimension.REPRODUCIBILITY,
            _indicator("env", IndicatorStatus.SKIPPED, None)))
        variant = _verdict(_dim(QualityDimension.REPRODUCIBILITY,
            _indicator("env", IndicatorStatus.PASS, 1.0)))
        comp = compare_verdicts(parent, variant)
        d = comp.dimension_deltas[0].indicator_deltas[0]
        assert d.change is IndicatorChange.INCOMPARABLE


class TestDimensionRollup:
    def test_dimension_with_one_regression_and_one_improvement(self):
        parent = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 60.0),
            _indicator("cc", IndicatorStatus.PASS, 5.0, comparator="le")))
        variant = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 75.0),     # improved
            _indicator("cc", IndicatorStatus.PASS, 8.0, comparator="le")))  # regressed
        comp = compare_verdicts(parent, variant)
        delta = comp.dimension_deltas[0]
        assert delta.any_improvement is True
        assert delta.any_regression is True

    def test_asymmetric_dimensions_handled(self):
        # Parent has Security, variant doesn't.
        parent = _verdict(_dim(QualityDimension.SECURITY,
            _indicator("bandit", IndicatorStatus.PASS, 0.0, comparator="le")))
        variant = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 70.0)))
        comp = compare_verdicts(parent, variant)
        # Both dimensions present in the output as placeholder deltas.
        dims = {d.dimension for d in comp.dimension_deltas}
        assert QualityDimension.SECURITY in dims
        assert QualityDimension.MAINTAINABILITY in dims


# ---------- StrictJudge ----------


class TestStrictJudge:
    def test_any_regression_means_regression(self):
        parent = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 70.0)))
        variant = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 60.0)))
        verdict = StrictJudge().decide(parent, variant)
        assert verdict.outcome is JudgeOutcome.REGRESSION
        assert verdict.strategy == "strict"

    def test_only_improvements_means_improvement(self):
        parent = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 60.0)))
        variant = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 75.0)))
        verdict = StrictJudge().decide(parent, variant)
        assert verdict.outcome is JudgeOutcome.IMPROVEMENT

    def test_no_movement_means_no_change(self):
        parent = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 70.0)))
        variant = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 70.0)))
        verdict = StrictJudge().decide(parent, variant)
        assert verdict.outcome is JudgeOutcome.NO_CHANGE

    def test_mixed_movement_is_regression(self):
        # One improved, one regressed: strict says regression wins.
        parent = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 60.0),
            _indicator("cc", IndicatorStatus.PASS, 5.0, comparator="le")))
        variant = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 75.0),     # improved
            _indicator("cc", IndicatorStatus.PASS, 9.0, comparator="le")))  # regressed
        verdict = StrictJudge().decide(parent, variant)
        assert verdict.outcome is JudgeOutcome.REGRESSION

    def test_explanation_lists_offending_indicators(self):
        parent = _verdict(_dim(QualityDimension.SECURITY,
            _indicator("bandit", IndicatorStatus.PASS, 0.0, comparator="le")))
        variant = _verdict(_dim(QualityDimension.SECURITY,
            _indicator("bandit", IndicatorStatus.PASS, 3.0, comparator="le")))
        verdict = StrictJudge().decide(parent, variant)
        assert "bandit" in verdict.explanation.lower()


# ---------- LexicographicJudge ----------


class TestLexicographicJudge:
    def test_high_priority_regression_blocks_lower_improvement(self):
        # Security regresses; Maintainability improves. Lex says regression.
        parent = _verdict(
            _dim(QualityDimension.SECURITY,
                _indicator("bandit", IndicatorStatus.PASS, 0.0, comparator="le")),
            _dim(QualityDimension.MAINTAINABILITY,
                _indicator("mi", IndicatorStatus.PASS, 60.0)),
        )
        variant = _verdict(
            _dim(QualityDimension.SECURITY,
                _indicator("bandit", IndicatorStatus.PASS, 2.0, comparator="le")),  # worse
            _dim(QualityDimension.MAINTAINABILITY,
                _indicator("mi", IndicatorStatus.PASS, 75.0)),  # better
        )
        verdict = LexicographicJudge().decide(parent, variant)
        assert verdict.outcome is JudgeOutcome.REGRESSION
        assert "security" in verdict.explanation.lower()

    def test_high_priority_improvement_outweighs_lower_regression(self):
        # Security improves; Maintainability regresses. Lex says improvement.
        parent = _verdict(
            _dim(QualityDimension.SECURITY,
                _indicator("bandit", IndicatorStatus.PASS, 3.0, comparator="le")),
            _dim(QualityDimension.MAINTAINABILITY,
                _indicator("mi", IndicatorStatus.PASS, 75.0)),
        )
        variant = _verdict(
            _dim(QualityDimension.SECURITY,
                _indicator("bandit", IndicatorStatus.PASS, 0.0, comparator="le")),  # better
            _dim(QualityDimension.MAINTAINABILITY,
                _indicator("mi", IndicatorStatus.PASS, 60.0)),  # worse
        )
        verdict = LexicographicJudge().decide(parent, variant)
        assert verdict.outcome is JudgeOutcome.IMPROVEMENT

    def test_no_change_when_nothing_moves(self):
        parent = _verdict(_dim(QualityDimension.SECURITY,
            _indicator("bandit", IndicatorStatus.PASS, 0.0, comparator="le")))
        variant = _verdict(_dim(QualityDimension.SECURITY,
            _indicator("bandit", IndicatorStatus.PASS, 0.0, comparator="le")))
        verdict = LexicographicJudge().decide(parent, variant)
        assert verdict.outcome is JudgeOutcome.NO_CHANGE


# ---------- ModelJudge ----------


def _make_llm_stub(content: str = "", error: str | None = None) -> MagicMock:
    """A stub LLM whose chat() returns a fixed LLMResponse."""
    llm = MagicMock()
    llm.name.return_value = "stub-judge-model"
    llm.chat.return_value = LLMResponse(
        content=content,
        model="stub-judge-model",
        provider="stub",
        input_tokens=10,
        output_tokens=20,
        error=error,
    )
    return llm


class TestModelJudge:
    def test_clean_json_response_parsed(self):
        llm = _make_llm_stub(content=(
            '{"outcome": "improvement", '
            '"explanation": "MI rose substantially.", '
            '"confidence": 0.87}'
        ))
        parent = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 60.0)))
        variant = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 75.0)))

        verdict = ModelJudge(llm=llm).decide(parent, variant)
        assert verdict.outcome is JudgeOutcome.IMPROVEMENT
        assert verdict.strategy == "model"
        assert verdict.confidence == 0.87
        assert verdict.fallback_used is False
        assert "MI rose" in verdict.explanation

    def test_json_inside_prose_is_recovered(self):
        # Models sometimes wrap JSON in markdown fences or extra prose.
        llm = _make_llm_stub(content=(
            "Sure, here is my verdict:\n"
            "```json\n"
            '{"outcome": "regression", "explanation": "Security dropped.", '
            '"confidence": 0.6}\n'
            "```\n"
            "Hope this helps."
        ))
        parent = _verdict(_dim(QualityDimension.SECURITY,
            _indicator("bandit", IndicatorStatus.PASS, 0.0, comparator="le")))
        variant = _verdict(_dim(QualityDimension.SECURITY,
            _indicator("bandit", IndicatorStatus.PASS, 2.0, comparator="le")))
        verdict = ModelJudge(llm=llm).decide(parent, variant)
        assert verdict.outcome is JudgeOutcome.REGRESSION
        assert verdict.fallback_used is False

    def test_unparseable_response_falls_back_to_strict(self):
        # No JSON at all. Strict fallback: should produce a regression
        # because Security indicator regressed.
        llm = _make_llm_stub(content="I cannot decide, sorry.")
        parent = _verdict(_dim(QualityDimension.SECURITY,
            _indicator("bandit", IndicatorStatus.PASS, 0.0, comparator="le")))
        variant = _verdict(_dim(QualityDimension.SECURITY,
            _indicator("bandit", IndicatorStatus.PASS, 2.0, comparator="le")))
        verdict = ModelJudge(llm=llm).decide(parent, variant)
        assert verdict.fallback_used is True
        assert verdict.outcome is JudgeOutcome.REGRESSION
        assert "fell back" in verdict.explanation.lower()

    def test_llm_exception_falls_back_to_strict(self):
        llm = MagicMock()
        llm.name.return_value = "stub-failing-model"
        llm.chat.side_effect = TimeoutError("network unreachable")
        parent = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 60.0)))
        variant = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 75.0)))
        verdict = ModelJudge(llm=llm).decide(parent, variant)
        assert verdict.fallback_used is True
        assert verdict.outcome is JudgeOutcome.IMPROVEMENT  # from strict rules
        assert "llm_error" in verdict.explanation.lower()

    def test_llm_error_field_triggers_fallback(self):
        # LLM returned cleanly but with an error attached.
        llm = _make_llm_stub(content="", error="rate_limited")
        parent = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 70.0)))
        variant = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 70.0)))
        verdict = ModelJudge(llm=llm).decide(parent, variant)
        assert verdict.fallback_used is True
        assert verdict.outcome is JudgeOutcome.NO_CHANGE

    def test_invalid_outcome_in_json_falls_back(self):
        llm = _make_llm_stub(content=(
            '{"outcome": "maybe", "explanation": "I am uncertain"}'
        ))
        parent = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 70.0)))
        variant = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 70.0)))
        verdict = ModelJudge(llm=llm).decide(parent, variant)
        assert verdict.fallback_used is True

    def test_confidence_clamped_to_unit_interval(self):
        llm = _make_llm_stub(content=(
            '{"outcome": "improvement", "explanation": "ok", "confidence": 3.5}'
        ))
        parent = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 60.0)))
        variant = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 75.0)))
        verdict = ModelJudge(llm=llm).decide(parent, variant)
        assert verdict.confidence == 1.0


# ---------- build_judge factory ----------


class TestBuildJudge:
    def test_strict(self):
        j = build_judge("strict")
        assert isinstance(j, StrictJudge)

    def test_lexicographic(self):
        j = build_judge(JudgeStrategy.LEXICOGRAPHIC)
        assert isinstance(j, LexicographicJudge)

    def test_model_requires_llm(self):
        with pytest.raises(ValueError, match="llm"):
            build_judge("model")

    def test_model_with_llm(self):
        llm = _make_llm_stub()
        j = build_judge("model", llm=llm)
        assert isinstance(j, ModelJudge)

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError):
            build_judge("definitely_not_a_strategy")


# ---------- JudgeVerdict serialisation ----------


class TestJudgeVerdictSerialisation:
    def test_to_dict_round_trips_outcome(self):
        parent = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 70.0)))
        variant = _verdict(_dim(QualityDimension.MAINTAINABILITY,
            _indicator("mi", IndicatorStatus.PASS, 70.0)))
        verdict = StrictJudge().decide(parent, variant)
        d = verdict.to_dict()
        assert d["outcome"] == "no_change"
        assert d["strategy"] == "strict"
        assert d["fallback_used"] is False
        assert "comparison" in d
