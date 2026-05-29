"""EVERSE quality profiles for QALLM.

A profile declares, for a given EOSC lifecycle stage, which EVERSE quality
dimensions to evaluate, which concrete indicators to compute per dimension,
and which repair prompt template to use when an indicator fails.

This module is pure declarative. It defines data classes and a default
profile (``IMPLEMENTATION_DEFAULT``). It deliberately does not import from
``qallm.orchestrator`` or ``qallm.analysis`` so that the rest of the codebase
can adopt it incrementally without circular imports.

References:
    EVERSE Research Software Quality Dimensions:
        https://everse.software/RSQKit/quality_dimensions
    EVERSE TechRadar:
        https://everse.software/TechRadar/
    Volentir et al., QRS 2025: role and lifecycle aware quality metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# EVERSE dimensions
# ---------------------------------------------------------------------------


class QualityDimension(str, Enum):
    """The EVERSE quality dimensions QALLM measures automatically in v1.

    The full EVERSE catalogue is broader (Usability, Performance,
    Compatibility, etc.). These five are the ones QALLM has tooling for:
    static metrics for Maintainability and Security, execution evidence
    for Reliability, project-shape checks for Reproducibility and FAIRness.
    """

    MAINTAINABILITY = "Maintainability"
    SECURITY = "Security"
    RELIABILITY = "Reliability"
    REPRODUCIBILITY = "Reproducibility"
    FAIRNESS = "FAIRness"


class LifecycleStage(str, Enum):
    """EOSC research software lifecycle stages.

    Mirrors ``qallm.analysis.normalizer.LifecycleStage`` deliberately. The
    duplication is acceptable for now: profiles is a leaf module and we want
    it importable without pulling in the analysis package. The two enums
    are kept in sync.
    """

    INITIALIZATION = "initialization"
    IMPLEMENTATION = "implementation"
    PUBLICATION = "publication"


class Comparator(str, Enum):
    """How to compare a measured value against a threshold."""

    GE = "ge"  # measured >= threshold means pass
    LE = "le"  # measured <= threshold means pass
    EQ = "eq"  # measured == threshold means pass

    def passes(self, measured: float, threshold: float) -> bool:
        if self is Comparator.GE:
            return measured >= threshold
        if self is Comparator.LE:
            return measured <= threshold
        return measured == threshold


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QualityIndicator:
    """A single measurable proxy for a quality dimension.

    Attributes:
        name: Stable identifier used in reports and the thesis appendix.
        evaluator: Dotted identifier of the evaluator that produces the value.
            Not imported here; the orchestrator resolves it.
        threshold: Numeric threshold the measured value is compared against.
        comparator: How to compare measured vs threshold.
        description: Short human-readable explanation for the report.
    """

    name: str
    evaluator: str
    threshold: float
    comparator: Comparator
    description: str = ""

    def passes(self, measured: float) -> bool:
        return self.comparator.passes(measured, self.threshold)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "evaluator": self.evaluator,
            "threshold": self.threshold,
            "comparator": self.comparator.value,
            "description": self.description,
        }


@dataclass(frozen=True)
class DimensionSpec:
    """The set of indicators QALLM evaluates for one EVERSE dimension."""

    dimension: QualityDimension
    indicators: tuple[QualityIndicator, ...]
    repair_prompt_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "indicators": [i.to_dict() for i in self.indicators],
            "repair_prompt_id": self.repair_prompt_id,
        }


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QualityProfile:
    """A named bundle of dimension specs valid for a lifecycle stage.

    Profiles are the integration surface between QALLM and the EVERSE
    vocabulary. A researcher selects a profile (or accepts the default for
    their lifecycle stage), and QALLM evaluates the named indicators.
    """

    profile_id: str
    lifecycle_stage: LifecycleStage
    dimensions: tuple[DimensionSpec, ...]
    description: str = ""

    def get_dimension(self, dimension: QualityDimension) -> DimensionSpec | None:
        for spec in self.dimensions:
            if spec.dimension is dimension:
                return spec
        return None

    def covers(self, dimension: QualityDimension) -> bool:
        return self.get_dimension(dimension) is not None

    def indicator_names(self) -> list[str]:
        return [ind.name for spec in self.dimensions for ind in spec.indicators]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "lifecycle_stage": self.lifecycle_stage.value,
            "description": self.description,
            "dimensions": [d.to_dict() for d in self.dimensions],
        }


# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------

# Thresholds for the IMPLEMENTATION stage (MI >= 60, CC <= 10) are the
# project's long-standing maintainability defaults, carried over from the
# original lifecycle normaliser. Reliability thresholds are taken from the
# pilot defaults.

IMPLEMENTATION_DEFAULT: QualityProfile = QualityProfile(
    profile_id="implementation_default",
    lifecycle_stage=LifecycleStage.IMPLEMENTATION,
    description=(
        "Default profile for research software at the implementation stage. "
        "Measures Maintainability and Security with static tools (Radon, "
        "Bandit), and Reliability and Reproducibility with the QALLM "
        "execution-based verification loop."
    ),
    dimensions=(
        DimensionSpec(
            dimension=QualityDimension.MAINTAINABILITY,
            repair_prompt_id="maintainability_repair_v1",
            indicators=(
                QualityIndicator(
                    name="maintainability_index",
                    evaluator="radon.mi",
                    threshold=60.0,
                    comparator=Comparator.GE,
                    description="Radon Maintainability Index, scale 0 to 100.",
                ),
                QualityIndicator(
                    name="cyclomatic_complexity",
                    evaluator="radon.cc",
                    threshold=10.0,
                    comparator=Comparator.LE,
                    description="Average per-function cyclomatic complexity.",
                ),
            ),
        ),
        DimensionSpec(
            dimension=QualityDimension.SECURITY,
            repair_prompt_id="security_repair_v1",
            indicators=(
                QualityIndicator(
                    name="bandit_high_findings",
                    evaluator="bandit.high",
                    threshold=0.0,
                    comparator=Comparator.LE,
                    description="Count of high-severity Bandit findings.",
                ),
                QualityIndicator(
                    name="bandit_cwe_classes",
                    evaluator="bandit.cwe_classes",
                    threshold=0.0,
                    comparator=Comparator.LE,
                    description="Number of distinct CWE weakness classes "
                    "flagged by Bandit (breadth of security issues).",
                ),
            ),
        ),
        DimensionSpec(
            dimension=QualityDimension.RELIABILITY,
            repair_prompt_id="reliability_repair_v1",
            indicators=(
                QualityIndicator(
                    name="test_pass_rate",
                    evaluator="qallm.verification.pass_rate",
                    threshold=0.9,
                    comparator=Comparator.GE,
                    description=(
                        "Fraction of generated tests that pass at the end of "
                        "the RL verification session."
                    ),
                ),
                QualityIndicator(
                    name="bugs_caught",
                    evaluator="qallm.verification.bugs",
                    threshold=0.0,
                    comparator=Comparator.GE,
                    description=(
                        "Count of distinct bugs surfaced by the verification "
                        "loop. Reported, not gated."
                    ),
                ),
            ),
        ),
        DimensionSpec(
            dimension=QualityDimension.REPRODUCIBILITY,
            repair_prompt_id="reproducibility_repair_v1",
            indicators=(
                QualityIndicator(
                    name="has_environment_manifest",
                    evaluator="qallm.repro.manifest",
                    threshold=1.0,
                    comparator=Comparator.GE,
                    description=(
                        "1 if a requirements.txt, environment.yml, or "
                        "pyproject.toml was found, 0 otherwise."
                    ),
                ),
                QualityIndicator(
                    name="deterministic_execution",
                    evaluator="qallm.repro.determinism",
                    threshold=1.0,
                    comparator=Comparator.GE,
                    description=(
                        "1 if repeated runs in the sandbox produce identical "
                        "test telemetry, 0 otherwise."
                    ),
                ),
            ),
        ),
        DimensionSpec(
            dimension=QualityDimension.FAIRNESS,
            repair_prompt_id="fairness_repair_v1",
            indicators=(
                QualityIndicator(
                    name="has_licence",
                    evaluator="qallm.fairness.licence",
                    threshold=1.0,
                    comparator=Comparator.GE,
                    description=(
                        "1 if a recognised licence file (LICENSE, LICENCE, "
                        "COPYING, etc.) is present at the project root, "
                        "0 otherwise."
                    ),
                ),
                QualityIndicator(
                    name="has_citation",
                    evaluator="qallm.fairness.citation",
                    threshold=1.0,
                    comparator=Comparator.GE,
                    description=(
                        "1 if CITATION.cff or CITATION.bib is present at "
                        "the project root, 0 otherwise."
                    ),
                ),
                QualityIndicator(
                    name="has_readme",
                    evaluator="qallm.fairness.readme",
                    threshold=1.0,
                    comparator=Comparator.GE,
                    description=(
                        "1 if a non-trivial README (>= 200 chars) exists "
                        "and contains description, installation, and usage "
                        "sections; 0 otherwise."
                    ),
                ),
                QualityIndicator(
                    name="docstring_coverage",
                    evaluator="qallm.fairness.docstring_coverage",
                    threshold=0.5,
                    comparator=Comparator.GE,
                    description=(
                        "Fraction of public functions, methods, and classes "
                        "with a non-empty docstring. Threshold 0.5."
                    ),
                ),
            ),
        ),
    ),
)


# ─── FAIR4RS profile (publication stage) ────────────────────────────
# A second real profile, to validate that the selector and the profile
# machinery generalise beyond one framework. FAIR4RS (FAIR principles for
# Research Software: Findable, Accessible, Interoperable, Reusable)
# emphasises sharing and reuse, so this profile targets the PUBLICATION
# lifecycle stage and leans on indicators QALLM already implements: the
# FAIRness probes (licence, citation, README, docstrings) and the
# Reproducibility probes (environment manifest, deterministic execution),
# which together speak to Accessibility and Reusability. Reliability is
# retained because reusable software must also be correct. Every indicator
# below uses a registered evaluator, so this profile actually runs; it is
# not a stub.
FAIR4RS_PUBLICATION: QualityProfile = QualityProfile(
    profile_id="fair4rs_publication",
    lifecycle_stage=LifecycleStage.PUBLICATION,
    description=(
        "FAIR4RS profile for research software at the publication and "
        "sharing stage. Emphasises Findability, Accessibility, and "
        "Reusability via FAIRness probes (licence, citation, README, "
        "docstrings) and Reproducibility probes (environment manifest, "
        "deterministic execution), with Reliability retained because "
        "reusable software must also be correct."
    ),
    dimensions=(
        DimensionSpec(
            dimension=QualityDimension.FAIRNESS,
            repair_prompt_id="fairness_repair_v1",
            indicators=(
                QualityIndicator(
                    name="has_licence",
                    evaluator="qallm.fairness.licence",
                    threshold=1.0,
                    comparator=Comparator.GE,
                    description="1 if a recognised licence file is present.",
                ),
                QualityIndicator(
                    name="has_citation",
                    evaluator="qallm.fairness.citation",
                    threshold=1.0,
                    comparator=Comparator.GE,
                    description="1 if CITATION.cff/.bib is present.",
                ),
                QualityIndicator(
                    name="has_readme",
                    evaluator="qallm.fairness.readme",
                    threshold=1.0,
                    comparator=Comparator.GE,
                    description="1 if a non-trivial, sectioned README exists.",
                ),
                QualityIndicator(
                    name="docstring_coverage",
                    evaluator="qallm.fairness.docstring_coverage",
                    threshold=0.7,
                    comparator=Comparator.GE,
                    description=(
                        "Fraction of public APIs with a docstring. Stricter "
                        "(0.7) than the implementation profile because "
                        "published software documents its public surface."
                    ),
                ),
            ),
        ),
        DimensionSpec(
            dimension=QualityDimension.REPRODUCIBILITY,
            repair_prompt_id="reproducibility_repair_v1",
            indicators=(
                QualityIndicator(
                    name="has_env_manifest",
                    evaluator="qallm.repro.manifest",
                    threshold=1.0,
                    comparator=Comparator.GE,
                    description=(
                        "1 if an environment manifest (requirements.txt, "
                        "environment.yml, pyproject.toml) is present."
                    ),
                ),
                QualityIndicator(
                    name="deterministic_execution",
                    evaluator="qallm.repro.determinism",
                    threshold=1.0,
                    comparator=Comparator.GE,
                    description=(
                        "1 if repeated execution of the generated tests "
                        "yields the same result."
                    ),
                ),
            ),
        ),
        DimensionSpec(
            dimension=QualityDimension.RELIABILITY,
            repair_prompt_id="reliability_repair_v1",
            indicators=(
                QualityIndicator(
                    name="test_pass_rate",
                    evaluator="qallm.verification.pass_rate",
                    threshold=0.9,
                    comparator=Comparator.GE,
                    description=(
                        "Fraction of generated tests passing at the end of "
                        "the verification session."
                    ),
                ),
            ),
        ),
    ),
)


_BUILT_IN: dict[str, QualityProfile] = {
    IMPLEMENTATION_DEFAULT.profile_id: IMPLEMENTATION_DEFAULT,
    FAIR4RS_PUBLICATION.profile_id: FAIR4RS_PUBLICATION,
}


def get_profile(profile_id: str) -> QualityProfile:
    """Look up a built-in profile by id.

    Raises:
        KeyError: If ``profile_id`` is not registered.
    """
    try:
        return _BUILT_IN[profile_id]
    except KeyError as exc:
        known = ", ".join(sorted(_BUILT_IN)) or "(none registered)"
        raise KeyError(
            f"Unknown profile '{profile_id}'. Known profiles: {known}."
        ) from exc


def list_profiles() -> list[str]:
    """Return the ids of all built-in profiles."""
    return sorted(_BUILT_IN)


def default_profile_for(stage: LifecycleStage) -> QualityProfile:
    """Return the default profile registered for a lifecycle stage.

    In v1 only ``IMPLEMENTATION`` has a built-in default. Other stages will
    fall back to it with a note; callers may register their own profiles.
    """
    for profile in _BUILT_IN.values():
        if profile.lifecycle_stage is stage:
            return profile
    return IMPLEMENTATION_DEFAULT


__all__ = [
    "Comparator",
    "DimensionSpec",
    "FAIR4RS_PUBLICATION",
    "IMPLEMENTATION_DEFAULT",
    "LifecycleStage",
    "QualityDimension",
    "QualityIndicator",
    "QualityProfile",
    "default_profile_for",
    "get_profile",
    "list_profiles",
]
