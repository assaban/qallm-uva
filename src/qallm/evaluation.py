"""Evaluator resolver and profile evaluation for QALLM.

This module turns a declarative :class:`qallm.profiles.QualityProfile` into
a concrete verdict. It does three things:

  * Maintains a registry of evaluator functions, each addressed by a stable
    string id (for example ``"radon.mi"``) referenced from a profile.
  * Resolves an evaluator id to a callable.
  * Walks a profile's dimensions and indicators, runs each evaluator
    against a code unit, and returns a typed :class:`ProfileVerdict`.

Design notes
------------

Evaluators have the signature ``(source: str, context: dict) -> float | None``.
A return value of ``None`` means the evaluator declined to produce a value
for this input (for example, the reproducibility evaluator without a
project root). The indicator is then marked ``SKIPPED`` in the verdict
rather than failing.

The built-in evaluators that wrap Radon and Bandit shell out using the
same commands and flags as :mod:`qallm.analysis.metrics`, so static
results are consistent between the legacy ``StaticAnalyzer`` and the new
profile-based path.

Verification-backed evaluators (``qallm.verification.pass_rate``,
``qallm.verification.bugs``) read a list of
:class:`~qallm.verification.models.TestGenerationSession` instances from
the evaluation context under the key ``"verification_sessions"``.
Callers that have not run verification can omit the key, in which case
the indicators are reported as ``SKIPPED``.

References
----------

EVERSE Research Software Quality Dimensions:
    https://everse.software/RSQKit/quality_dimensions
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from qallm.profiles import (
    DimensionSpec,
    QualityDimension,
    QualityIndicator,
    QualityProfile,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class IndicatorStatus(str, Enum):
    """Outcome of evaluating one indicator."""

    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class IndicatorResult:
    """The result of evaluating one indicator."""

    name: str
    evaluator: str
    threshold: float
    comparator: str
    measured: float | None
    status: IndicatorStatus
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "evaluator": self.evaluator,
            "threshold": self.threshold,
            "comparator": self.comparator,
            "measured": self.measured,
            "status": self.status.value,
            "detail": self.detail,
        }


@dataclass
class DimensionResult:
    """The roll-up across all indicators of one dimension."""

    dimension: QualityDimension
    indicators: list[IndicatorResult] = field(default_factory=list)

    @property
    def status(self) -> IndicatorStatus:
        """Dimension status is the worst non-skipped indicator status.

        If every indicator was skipped, the dimension is SKIPPED. If any
        errored, the dimension is ERROR. Otherwise, FAIL if any failed,
        else PASS.
        """
        statuses = [ind.status for ind in self.indicators]
        if not statuses:
            return IndicatorStatus.SKIPPED
        if all(s is IndicatorStatus.SKIPPED for s in statuses):
            return IndicatorStatus.SKIPPED
        if any(s is IndicatorStatus.ERROR for s in statuses):
            return IndicatorStatus.ERROR
        if any(s is IndicatorStatus.FAIL for s in statuses):
            return IndicatorStatus.FAIL
        return IndicatorStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "status": self.status.value,
            "indicators": [i.to_dict() for i in self.indicators],
        }


@dataclass
class ProfileVerdict:
    """The result of evaluating a full :class:`QualityProfile`."""

    profile_id: str
    dimensions: list[DimensionResult] = field(default_factory=list)

    @property
    def status(self) -> IndicatorStatus:
        """Overall status follows the same worst-of rule as dimensions."""
        statuses = [d.status for d in self.dimensions]
        if not statuses:
            return IndicatorStatus.SKIPPED
        if all(s is IndicatorStatus.SKIPPED for s in statuses):
            return IndicatorStatus.SKIPPED
        if any(s is IndicatorStatus.ERROR for s in statuses):
            return IndicatorStatus.ERROR
        if any(s is IndicatorStatus.FAIL for s in statuses):
            return IndicatorStatus.FAIL
        return IndicatorStatus.PASS

    def get_dimension(
        self, dimension: QualityDimension
    ) -> DimensionResult | None:
        for d in self.dimensions:
            if d.dimension is dimension:
                return d
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "status": self.status.value,
            "dimensions": [d.to_dict() for d in self.dimensions],
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


# An evaluator takes the source string and a context dict, and returns a
# float (the measured value) or None (declined / not applicable).
EvaluatorFn = Callable[[str, dict[str, Any]], float | None]


_REGISTRY: dict[str, EvaluatorFn] = {}


def register(evaluator_id: str, fn: EvaluatorFn) -> None:
    """Register an evaluator function under a stable string id.

    Overwrites any previous registration. Used both for built-ins (below)
    and for tests that want to inject a stub.
    """
    _REGISTRY[evaluator_id] = fn


def resolve(evaluator_id: str) -> EvaluatorFn:
    """Look up an evaluator by id.

    Raises:
        KeyError: if no evaluator is registered under ``evaluator_id``.
    """
    try:
        return _REGISTRY[evaluator_id]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(
            f"Unknown evaluator '{evaluator_id}'. Registered evaluators: "
            f"{known}."
        ) from exc


def registered_evaluators() -> list[str]:
    """Return the ids of all registered evaluators, sorted."""
    return sorted(_REGISTRY)


# ---------------------------------------------------------------------------
# Built-in evaluators
# ---------------------------------------------------------------------------


def _radon_mi(source: str, context: dict[str, Any]) -> float | None:
    """Maintainability Index via Radon. Returns a float on the 0 to 100 scale."""
    if not source.strip():
        return None
    try:
        result = subprocess.run(
            ["radon", "mi", "-j", "-"],
            input=source,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        data = json.loads(result.stdout)
        val = next(iter(data.values()))
        if isinstance(val, dict) and "mi" in val:
            return float(val["mi"])
        if isinstance(val, (int, float)):
            return float(val)
    except (json.JSONDecodeError, StopIteration, ValueError, TypeError):
        return None
    return None


def _radon_cc(source: str, context: dict[str, Any]) -> float | None:
    """Average cyclomatic complexity per function via Radon."""
    if not source.strip():
        return None
    try:
        result = subprocess.run(
            ["radon", "cc", "-j", "-"],
            input=source,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        data = json.loads(result.stdout)
        blocks = next(iter(data.values()))
        if not blocks:
            # No functions defined; treat as zero complexity, not skipped.
            return 0.0
        return sum(b.get("complexity", 0) for b in blocks) / len(blocks)
    except (json.JSONDecodeError, StopIteration, ZeroDivisionError, TypeError):
        return None


def _bandit_high(source: str, context: dict[str, Any]) -> float | None:
    """Count of HIGH-severity Bandit findings on the source."""
    if not source.strip():
        return None
    try:
        result = subprocess.run(
            ["bandit", "-r", "-f", "json", "-q", "-"],
            input=source,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if not result.stdout.strip():
        return None
    try:
        data = json.loads(result.stdout)
        results = data.get("results", [])
        return float(
            sum(1 for r in results if r.get("issue_severity") == "HIGH")
        )
    except (json.JSONDecodeError, TypeError):
        return None


def _bandit_cwe_classes(source: str, context: dict[str, Any]) -> float | None:
    """Number of distinct CWE classes flagged by Bandit on the source.

    Complements ``bandit.high`` (which counts findings by severity) with a
    breadth signal: how many *different* weakness classes (by CWE id) the
    static scan surfaced. A repaired variant that closes a whole CWE class
    scores better here even if the raw finding count is unchanged. Returns
    ``None`` (SKIP) when Bandit cannot run or produces no parseable output,
    and ``0.0`` when it ran cleanly with no CWE-tagged findings.
    """
    if not source.strip():
        return None
    try:
        result = subprocess.run(
            ["bandit", "-r", "-f", "json", "-q", "-"],
            input=source,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if not result.stdout.strip():
        return None
    try:
        data = json.loads(result.stdout)
        results = data.get("results", [])
        cwe_ids = set()
        for r in results:
            cwe = r.get("issue_cwe") or {}
            cwe_id = cwe.get("id") if isinstance(cwe, dict) else None
            if cwe_id is not None:
                cwe_ids.add(cwe_id)
        return float(len(cwe_ids))
    except (json.JSONDecodeError, TypeError):
        return None


_MANIFEST_NAMES = ("requirements.txt", "environment.yml", "pyproject.toml")


def _repro_manifest(source: str, context: dict[str, Any]) -> float | None:
    """1.0 if a recognised environment manifest exists under ``project_root``.

    Returns ``None`` if no project root is supplied: reproducibility is a
    property of a project, not of a snippet, and we'd rather skip than
    fabricate.
    """
    root = context.get("project_root")
    if root is None:
        return None
    root_path = Path(root)
    if not root_path.exists():
        return None
    for name in _MANIFEST_NAMES:
        if (root_path / name).exists():
            return 1.0
    return 0.0


def _repro_determinism(source: str, context: dict[str, Any]) -> float | None:
    """Determinism check is sandbox-backed; skipped at the evaluator level.

    The verification sandbox already runs each test session once.
    Determinism would require a second run and a comparison. That is not
    free, and we don't want plain profile evaluation to silently invoke
    it. Returns ``None`` so the indicator is reported as SKIPPED until
    a follow-up wires this in explicitly.
    """
    return None


def _verification_pass_rate(source: str, context: dict[str, Any]) -> float | None:
    """Reliability indicator: average test pass rate across function sessions.

    Reads ``context["verification_sessions"]`` (a list of
    :class:`TestGenerationSession`). Returns the mean of each session's
    ``final_pass_rate``, skipping sessions whose pass rate is undefined
    (no rounds or zero passed+failed tests).

    Returns ``None`` if the context has no sessions key, or if every session
    has an undefined pass rate. This is consistent with the SKIPPED semantics
    elsewhere in the module.
    """
    sessions = context.get("verification_sessions")
    if not sessions:
        return None
    rates = [
        s.final_pass_rate for s in sessions if s.final_pass_rate is not None
    ]
    if not rates:
        return None
    return sum(rates) / len(rates)


def _verification_bugs(source: str, context: dict[str, Any]) -> float | None:
    """Reliability indicator: total bugs caught across function sessions.

    Reads ``context["verification_sessions"]`` (a list of
    :class:`TestGenerationSession`). Returns the sum of each session's
    ``final_bugs`` as a float. Returns ``None`` only if there is no
    sessions key at all; an empty list yields ``0.0`` because "we ran
    verification and found no bugs" is a meaningful zero, not a SKIP.
    """
    sessions = context.get("verification_sessions")
    if sessions is None:
        return None
    return float(sum(s.final_bugs for s in sessions))


def _sonar_measure(context: dict[str, Any], key: str) -> float | None:
    """Read one SonarQube measure from context, or None if unavailable.

    The orchestrator places the analysed unit's SonarQube measures (parsed
    from the analyzer's RawToolResult) under ``context["sonar_measures"]``
    when a SonarQube server is configured. When it is not, the key is
    absent and these evaluators skip, so the iso25010_base profile falls
    back to its Radon/Bandit indicators (the complement-with-fallback
    decision). SonarQube ratings are 1.0=A (best) .. 5.0=E (worst).
    """
    measures = context.get("sonar_measures")
    if not measures or key not in measures:
        return None
    try:
        return float(measures[key])
    except (TypeError, ValueError):
        return None


def _sonar_reliability_rating(source: str, context: dict[str, Any]) -> float | None:
    return _sonar_measure(context, "reliability_rating")


def _sonar_security_rating(source: str, context: dict[str, Any]) -> float | None:
    return _sonar_measure(context, "security_rating")


def _sonar_maintainability_rating(source: str, context: dict[str, Any]) -> float | None:
    # SonarQube exposes the maintainability rating under sqale_rating.
    return _sonar_measure(context, "sqale_rating")


def _not_measured(source: str, context: dict[str, Any]) -> float | None:
    """Always declines, marking the indicator SKIPPED.

    Used for quality characteristics a profile declares to stay faithful
    to a standard (e.g. the ISO/IEC 25010 characteristics QALLM does not
    yet measure) without claiming a measurement it cannot make. SKIPPED is
    the honest state: in-model, not assessed.
    """
    return None


def _register_builtins() -> None:
    register("radon.mi", _radon_mi)
    register("radon.cc", _radon_cc)
    register("bandit.high", _bandit_high)
    register("bandit.cwe_classes", _bandit_cwe_classes)
    register("qallm.not_measured", _not_measured)
    register("sonar.reliability_rating", _sonar_reliability_rating)
    register("sonar.security_rating", _sonar_security_rating)
    register("sonar.maintainability_rating", _sonar_maintainability_rating)
    register("qallm.repro.manifest", _repro_manifest)
    register("qallm.repro.determinism", _repro_determinism)
    register("qallm.verification.pass_rate", _verification_pass_rate)
    register("qallm.verification.bugs", _verification_bugs)
    # FAIRness indicators live in qallm.fairness; imported here to keep
    # the indicator module thin and avoid a circular import.
    from qallm.fairness import (
        _fairness_citation,
        _fairness_docstring_coverage,
        _fairness_licence,
        _fairness_readme,
    )
    register("qallm.fairness.licence", _fairness_licence)
    # American spelling is the same evaluator; profiles in either dialect work.
    register("qallm.fairness.license", _fairness_licence)
    register("qallm.fairness.citation", _fairness_citation)
    register("qallm.fairness.readme", _fairness_readme)
    register("qallm.fairness.docstring_coverage", _fairness_docstring_coverage)


_register_builtins()


# ---------------------------------------------------------------------------
# Profile evaluation
# ---------------------------------------------------------------------------


def _evaluate_indicator(
    indicator: QualityIndicator, source: str, context: dict[str, Any]
) -> IndicatorResult:
    """Run one indicator's evaluator, return a typed result.

    Any exception inside the evaluator is captured and reported as ERROR
    rather than propagated, because a single broken evaluator should not
    take down a profile evaluation.
    """
    try:
        fn = resolve(indicator.evaluator)
    except KeyError as exc:
        return IndicatorResult(
            name=indicator.name,
            evaluator=indicator.evaluator,
            threshold=indicator.threshold,
            comparator=indicator.comparator.value,
            measured=None,
            status=IndicatorStatus.ERROR,
            detail=str(exc),
        )

    try:
        measured = fn(source, context)
    except Exception as exc:  # noqa: BLE001 - we want to capture all failures
        return IndicatorResult(
            name=indicator.name,
            evaluator=indicator.evaluator,
            threshold=indicator.threshold,
            comparator=indicator.comparator.value,
            measured=None,
            status=IndicatorStatus.ERROR,
            detail=f"{type(exc).__name__}: {exc}",
        )

    if measured is None:
        return IndicatorResult(
            name=indicator.name,
            evaluator=indicator.evaluator,
            threshold=indicator.threshold,
            comparator=indicator.comparator.value,
            measured=None,
            status=IndicatorStatus.SKIPPED,
            detail="Evaluator declined to produce a value for this input.",
        )

    passed = indicator.passes(measured)
    return IndicatorResult(
        name=indicator.name,
        evaluator=indicator.evaluator,
        threshold=indicator.threshold,
        comparator=indicator.comparator.value,
        measured=float(measured),
        status=IndicatorStatus.PASS if passed else IndicatorStatus.FAIL,
        detail="",
    )


def _evaluate_dimension(
    spec: DimensionSpec, source: str, context: dict[str, Any]
) -> DimensionResult:
    return DimensionResult(
        dimension=spec.dimension,
        indicators=[
            _evaluate_indicator(ind, source, context) for ind in spec.indicators
        ],
    )


def evaluate_profile(
    profile: QualityProfile,
    source: str,
    *,
    context: dict[str, Any] | None = None,
) -> ProfileVerdict:
    """Run every indicator in ``profile`` against ``source``.

    Args:
        profile: The :class:`QualityProfile` to evaluate.
        source: Python source code as a string.
        context: Optional context bag passed to each evaluator. Recognised
            keys include ``project_root`` (path-like) for reproducibility
            evaluators. Extra keys are ignored by evaluators that don't
            need them.

    Returns:
        A :class:`ProfileVerdict` whose ``status`` is the worst-of across
        all non-skipped dimensions.
    """
    ctx: dict[str, Any] = dict(context or {})
    return ProfileVerdict(
        profile_id=profile.profile_id,
        dimensions=[
            _evaluate_dimension(spec, source, ctx) for spec in profile.dimensions
        ],
    )


__all__ = [
    "DimensionResult",
    "EvaluatorFn",
    "IndicatorResult",
    "IndicatorStatus",
    "ProfileVerdict",
    "evaluate_profile",
    "register",
    "registered_evaluators",
    "resolve",
]
