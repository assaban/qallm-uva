"""The QALLM judge: decides whether a repaired variant improves on its parent.

See workflow design v3 sections 5 and 9.1-9.3 for the full design discussion.

Public API
----------

Construct a strategy:

    from qallm.judge import StrictJudge, LexicographicJudge, ModelJudge

Each strategy implements::

    def decide(parent: ProfileVerdict,
               variant: ProfileVerdict,
               *,
               raw_evidence: dict | None = None) -> JudgeVerdict

The returned :class:`JudgeVerdict` has:

  * ``outcome``: IMPROVEMENT, REGRESSION, or NO_CHANGE.
  * ``deltas``: structured per-indicator and per-dimension comparison.
  * ``explanation``: human-readable reason, either rule-derived (Strict,
    Lexicographic) or LLM-generated (Model).
  * ``strategy``: which strategy produced this verdict.
  * ``fallback_used``: True if a Model strategy fell back to Strict due to
    an LLM failure.

The deltas object is always populated, regardless of strategy. This is
deliberate: the thesis-quality validation argument (workflow design v3
section 5.2) requires that every model verdict can be compared against the
raw numerical comparison side-by-side.
"""

from qallm.judge.models import (
    DimensionDelta,
    IndicatorDelta,
    JudgeOutcome,
    JudgeVerdict,
    VerdictComparison,
)
from qallm.judge.strategies import (
    JudgeStrategy,
    LexicographicJudge,
    ModelJudge,
    StrictJudge,
    build_judge,
)

__all__ = [
    "DimensionDelta",
    "IndicatorDelta",
    "JudgeOutcome",
    "JudgeStrategy",
    "JudgeVerdict",
    "LexicographicJudge",
    "ModelJudge",
    "StrictJudge",
    "VerdictComparison",
    "build_judge",
]
