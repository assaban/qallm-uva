"""Legacy lifecycle normaliser. Retained for reference and back-compat only.

This module predates the EVERSE profile system. The authoritative way to
evaluate code against a quality standard is now
:func:`qallm.evaluation.evaluate_profile` driven by a
:class:`qallm.profiles.QualityProfile`. See ``docs/workflow-design.md``.

What remains here:

* :class:`LifecycleStage` is re-exported from :mod:`qallm.profiles` so the
  whole codebase shares one enum. The previous duplicate definition (kept
  in sync by hand) has been removed. Importing it from here continues to
  work for existing call sites.
* :class:`LifecycleNormalizer` is the original hardcoded-threshold
  evaluator. It is deprecated: it is not used anywhere in the pipeline and
  is kept only so its thresholds remain documented and its unit test keeps
  passing. New code must not use it; use a ``QualityProfile`` instead.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict

# Single source of truth for the lifecycle stages. Defined in profiles so
# that module stays a dependency-light leaf; re-exported here so the many
# existing ``from qallm.analysis.normalizer import LifecycleStage`` call
# sites keep working unchanged.
from qallm.profiles import LifecycleStage

__all__ = ["LifecycleStage", "LifecycleNormalizer"]


class LifecycleNormalizer:
    """Deprecated. Hardcoded-threshold lifecycle evaluator.

    Superseded by :func:`qallm.evaluation.evaluate_profile`. The thresholds
    below are mirrored, for the IMPLEMENTATION stage, by the
    ``IMPLEMENTATION_DEFAULT`` profile in :mod:`qallm.profiles`. This class
    is retained only for historical reference and to keep its unit test
    meaningful; it is not wired into the orchestrator or the web API.
    """

    # Maintainability thresholds per lifecycle stage (MI floor, CC ceiling).
    THRESHOLDS = {
        LifecycleStage.INITIALIZATION: {"mi": 40.0, "cc": 15.0},
        LifecycleStage.IMPLEMENTATION: {"mi": 60.0, "cc": 10.0},
        LifecycleStage.PUBLICATION: {"mi": 80.0, "cc": 5.0},
    }

    def __init__(self) -> None:
        warnings.warn(
            "LifecycleNormalizer is deprecated; evaluate quality with a "
            "QualityProfile via qallm.evaluation.evaluate_profile instead.",
            DeprecationWarning,
            stacklevel=2,
        )

    def evaluate(self, metrics: Dict[str, Any], stage: LifecycleStage) -> str:
        mi = metrics.get("mi", 0)
        cc = metrics.get("cc", 99)

        limit = self.THRESHOLDS.get(stage)

        if mi >= limit["mi"] and cc <= limit["cc"]:
            return "PASSED"
        elif mi >= (limit["mi"] * 0.8):
            return "WARNING"
        return "REFINEMENT_REQUIRED"
