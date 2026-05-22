"""Three judge strategies: Strict, Lexicographic, Model.

Each strategy implements the same shape::

    def decide(parent: ProfileVerdict,
               variant: ProfileVerdict,
               *,
               raw_evidence: dict | None = None) -> JudgeVerdict

The strategies share the comparison logic from :mod:`qallm.judge.comparator`;
they differ in how they map a comparison to an outcome.

Workflow design v3 section 9.3 defines the three strategies and the
priority ordering for Lexicographic.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Protocol

from qallm.evaluation import ProfileVerdict
from qallm.judge.comparator import compare_verdicts
from qallm.judge.models import (
    DimensionDelta,
    IndicatorChange,
    JudgeOutcome,
    JudgeVerdict,
    VerdictComparison,
)
from qallm.judge.prompts import SYSTEM_PROMPT, build_user_prompt
from qallm.llm.base import LLMModel, TokenTracker
from qallm.profiles import QualityDimension


logger = logging.getLogger(__name__)


# ---------- shared lexicographic ordering ----------

# Higher priority first. Workflow design v3 section 9.3.
#
# v1 priority covers the four EVERSE dimensions currently implemented.
# FAIRness will be added by NEW-04; it slots in at the end (lowest priority)
# without changing the order of the others.
DEFAULT_DIMENSION_PRIORITY: tuple[QualityDimension, ...] = (
    QualityDimension.SECURITY,
    QualityDimension.RELIABILITY,
    QualityDimension.MAINTAINABILITY,
    QualityDimension.REPRODUCIBILITY,
)


class JudgeStrategy(str, Enum):
    """The three configurable strategies. Used at orchestrator startup."""

    STRICT = "strict"
    LEXICOGRAPHIC = "lexicographic"
    MODEL = "model"


# ---------- protocol that all strategies satisfy ----------


class Judge(Protocol):
    """Common shape for every strategy."""

    def decide(
        self,
        parent: ProfileVerdict,
        variant: ProfileVerdict,
        *,
        raw_evidence: dict[str, Any] | None = None,
    ) -> JudgeVerdict: ...


# ---------- StrictJudge ----------


@dataclass
class StrictJudge:
    """Any indicator regression anywhere blocks acceptance.

    Deterministic; no LLM call. Useful as a baseline and as the fallback
    for ModelJudge when an LLM call fails.
    """

    strategy_name: str = "strict"

    def decide(
        self,
        parent: ProfileVerdict,
        variant: ProfileVerdict,
        *,
        raw_evidence: dict[str, Any] | None = None,
    ) -> JudgeVerdict:
        comparison = compare_verdicts(parent, variant)

        if comparison.any_regression:
            outcome = JudgeOutcome.REGRESSION
            explanation = _summarise_regressions(comparison, prefix="Strict: ")
        elif comparison.any_improvement:
            outcome = JudgeOutcome.IMPROVEMENT
            explanation = _summarise_improvements(comparison, prefix="Strict: ")
        else:
            outcome = JudgeOutcome.NO_CHANGE
            explanation = (
                "Strict: no indicator improved or regressed; "
                "the comparison is neutral."
            )

        return JudgeVerdict(
            outcome=outcome,
            strategy=self.strategy_name,
            explanation=explanation,
            comparison=comparison,
        )


# ---------- LexicographicJudge ----------


@dataclass
class LexicographicJudge:
    """Dimensions ranked by priority; high-priority regressions block.

    A high-priority dimension regression makes the verdict REGRESSION
    regardless of any low-priority improvements. A low-priority regression
    is tolerated if a higher-priority dimension improved.

    Default priority: SECURITY > RELIABILITY > MAINTAINABILITY >
    REPRODUCIBILITY > FAIRNESS. Configurable via the ``priority`` field.
    """

    priority: tuple[QualityDimension, ...] = DEFAULT_DIMENSION_PRIORITY
    strategy_name: str = "lexicographic"

    def decide(
        self,
        parent: ProfileVerdict,
        variant: ProfileVerdict,
        *,
        raw_evidence: dict[str, Any] | None = None,
    ) -> JudgeVerdict:
        comparison = compare_verdicts(parent, variant)
        outcome, explanation = self._evaluate(comparison)
        return JudgeVerdict(
            outcome=outcome,
            strategy=self.strategy_name,
            explanation=explanation,
            comparison=comparison,
        )

    def _evaluate(self, comparison: VerdictComparison) -> tuple[JudgeOutcome, str]:
        by_dim = {d.dimension: d for d in comparison.dimension_deltas}

        # Walk priorities in order. The first dimension that has either an
        # improvement or a regression determines the verdict; lower-priority
        # dimensions are tie-breakers.
        for dim in self.priority:
            delta = by_dim.get(dim)
            if delta is None:
                continue
            if delta.any_regression:
                return (
                    JudgeOutcome.REGRESSION,
                    (
                        f"Lexicographic: regression in {dim.value}, "
                        f"the highest-priority dimension showing change. "
                        + _summarise_regressions(comparison)
                    ),
                )
            if delta.any_improvement:
                return (
                    JudgeOutcome.IMPROVEMENT,
                    (
                        f"Lexicographic: improvement in {dim.value}, "
                        f"the highest-priority dimension showing change. "
                        + _summarise_improvements(comparison)
                    ),
                )

        # No priority dimension changed. Check whether any non-priority
        # dimension shows movement.
        priority_set = set(self.priority)
        for delta in comparison.dimension_deltas:
            if delta.dimension in priority_set:
                continue
            if delta.any_regression:
                return (
                    JudgeOutcome.REGRESSION,
                    f"Lexicographic: regression in {delta.dimension.value} "
                    "(not in priority list).",
                )
            if delta.any_improvement:
                return (
                    JudgeOutcome.IMPROVEMENT,
                    f"Lexicographic: improvement in {delta.dimension.value} "
                    "(not in priority list).",
                )

        return (
            JudgeOutcome.NO_CHANGE,
            "Lexicographic: no dimension shows improvement or regression.",
        )


# ---------- ModelJudge ----------


@dataclass
class ModelJudge:
    """LLM-driven judge with structured output and a Strict fallback.

    The model receives a JSON payload describing the comparison plus any
    raw evidence; it must respond with a JSON object having
    {outcome, explanation, confidence}. On parse failure or LLM error the
    judge falls back to :class:`StrictJudge` and sets ``fallback_used`` so
    the failure is visible in the artefact.

    The ``tracker`` argument is optional; if supplied, the judge's LLM
    calls are recorded there for cost accounting.
    """

    llm: LLMModel
    tracker: TokenTracker | None = None
    strategy_name: str = "model"

    def decide(
        self,
        parent: ProfileVerdict,
        variant: ProfileVerdict,
        *,
        raw_evidence: dict[str, Any] | None = None,
    ) -> JudgeVerdict:
        comparison = compare_verdicts(parent, variant)
        user_prompt = build_user_prompt(comparison, raw_evidence)

        try:
            response = self.llm.chat(
                system=SYSTEM_PROMPT,
                user=user_prompt,
                tracker=self.tracker,
            )
        except Exception as exc:  # noqa: BLE001 - any LLM failure
            logger.warning(
                "ModelJudge: LLM call failed (%s: %s); falling back to Strict.",
                type(exc).__name__,
                exc,
            )
            return self._fallback(comparison, reason=f"llm_error: {exc}")

        if response.error:
            logger.warning(
                "ModelJudge: LLM responded with error '%s'; falling back to Strict.",
                response.error,
            )
            return self._fallback(comparison, reason=f"llm_error: {response.error}")

        parsed = _parse_model_response(response.content or "")
        if parsed is None:
            logger.warning(
                "ModelJudge: failed to parse JSON from response; falling back to Strict. "
                "Response was: %r",
                (response.content or "")[:300],
            )
            return self._fallback(
                comparison,
                reason="parse_failed",
                raw_response=response.content,
            )

        outcome, explanation, confidence = parsed
        return JudgeVerdict(
            outcome=outcome,
            strategy=self.strategy_name,
            explanation=explanation,
            comparison=comparison,
            model_raw_response=response.content,
            judge_model=response.model or self.llm.name(),
            confidence=confidence,
        )

    def _fallback(
        self,
        comparison: VerdictComparison,
        *,
        reason: str,
        raw_response: str | None = None,
    ) -> JudgeVerdict:
        # Re-derive a verdict from the comparison via strict rules so we
        # still emit a deterministic outcome.
        if comparison.any_regression:
            outcome = JudgeOutcome.REGRESSION
            why = _summarise_regressions(comparison)
        elif comparison.any_improvement:
            outcome = JudgeOutcome.IMPROVEMENT
            why = _summarise_improvements(comparison)
        else:
            outcome = JudgeOutcome.NO_CHANGE
            why = "no indicator improved or regressed."

        return JudgeVerdict(
            outcome=outcome,
            strategy=self.strategy_name,
            explanation=(
                f"ModelJudge fell back to Strict ({reason}). Strict verdict: {why}"
            ),
            comparison=comparison,
            model_raw_response=raw_response,
            judge_model=self.llm.name(),
            fallback_used=True,
        )


# ---------- factory ----------


def build_judge(
    strategy: JudgeStrategy | str,
    *,
    llm: LLMModel | None = None,
    tracker: TokenTracker | None = None,
    priority: tuple[QualityDimension, ...] = DEFAULT_DIMENSION_PRIORITY,
) -> Judge:
    """Construct a judge from a strategy string or enum.

    Raises:
        ValueError: if ``strategy`` is "model" but ``llm`` is None.
    """
    s = JudgeStrategy(strategy) if isinstance(strategy, str) else strategy
    if s is JudgeStrategy.STRICT:
        return StrictJudge()
    if s is JudgeStrategy.LEXICOGRAPHIC:
        return LexicographicJudge(priority=priority)
    if s is JudgeStrategy.MODEL:
        if llm is None:
            raise ValueError("ModelJudge requires an `llm` argument.")
        return ModelJudge(llm=llm, tracker=tracker)
    raise ValueError(f"Unknown strategy: {strategy!r}")


# ---------- helpers ----------


def _summarise_regressions(
    comparison: VerdictComparison, prefix: str = ""
) -> str:
    names = []
    for d in comparison.dimension_deltas:
        for ind in d.indicator_deltas:
            if ind.change is IndicatorChange.REGRESSED:
                names.append(f"{d.dimension.value}.{ind.name}")
    if not names:
        return f"{prefix}no indicator regressed."
    return f"{prefix}regressions: {', '.join(names)}."


def _summarise_improvements(
    comparison: VerdictComparison, prefix: str = ""
) -> str:
    names = []
    for d in comparison.dimension_deltas:
        for ind in d.indicator_deltas:
            if ind.change is IndicatorChange.IMPROVED:
                names.append(f"{d.dimension.value}.{ind.name}")
    if not names:
        return f"{prefix}no indicator improved."
    return f"{prefix}improvements: {', '.join(names)}."


# ---------- response parsing ----------


def _parse_model_response(
    content: str,
) -> Optional[tuple[JudgeOutcome, str, float | None]]:
    """Extract (outcome, explanation, confidence) from the model output.

    Tries: full JSON parse, then JSON parse of the first ``{...}`` block
    found in the text. Returns None if both fail or the outcome is invalid.
    """
    obj = _try_parse_json(content)
    if obj is None:
        return None
    raw_outcome = obj.get("outcome")
    if not isinstance(raw_outcome, str):
        return None
    try:
        outcome = JudgeOutcome(raw_outcome.lower().strip())
    except ValueError:
        return None
    explanation = obj.get("explanation")
    if not isinstance(explanation, str):
        explanation = ""
    raw_conf = obj.get("confidence")
    confidence: float | None = None
    if isinstance(raw_conf, (int, float)):
        confidence = max(0.0, min(1.0, float(raw_conf)))
    return outcome, explanation, confidence


_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}", re.MULTILINE)


def _try_parse_json(text: str) -> dict | None:
    """Try a strict parse, then a regex-fallback to find a JSON-shaped block."""
    text = text.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # Some models wrap JSON in markdown fences or prose. Find the first
    # `{...}` blob and try parsing that.
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None
