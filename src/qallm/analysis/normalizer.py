"""Lifecycle stage enum, re-exported for back-compat.

This module predated the EVERSE profile system. The authoritative way to
evaluate code against a quality standard is now
:func:`qallm.evaluation.evaluate_profile` driven by a
:class:`qallm.profiles.QualityProfile`. See ``docs/architecture/workflow-design.md``.

The former ``LifecycleNormalizer`` (a hardcoded-threshold evaluator) has
been removed; it was superseded by the profile system and was no longer
used anywhere in the pipeline. Its IMPLEMENTATION-stage thresholds live on
in the ``IMPLEMENTATION_DEFAULT`` profile in :mod:`qallm.profiles`.

:class:`LifecycleStage` is re-exported from :mod:`qallm.profiles` so the
whole codebase shares one enum and existing
``from qallm.analysis.normalizer import LifecycleStage`` call sites keep
working unchanged.
"""

from __future__ import annotations

# Single source of truth for the lifecycle stages. Defined in profiles so
# that module stays a dependency-light leaf; re-exported here for the
# existing call sites.
from qallm.profiles import LifecycleStage

__all__ = ["LifecycleStage"]
