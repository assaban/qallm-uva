"""Tests for the ISO/IEC 25010 base quality profile."""

from qallm.evaluation import evaluate_profile, resolve
from qallm.profiles import (
    ISO25010_BASE,
    QualityDimension,
    get_profile,
    list_profiles,
)


def test_iso25010_registered():
    assert "iso25010_base" in list_profiles()
    assert get_profile("iso25010_base") is ISO25010_BASE


def test_declares_all_nine_iso_characteristics():
    # ISO/IEC 25010:2023 has nine product-quality characteristics. The
    # profile must declare all nine for fidelity to the standard.
    nine = {
        QualityDimension.FUNCTIONAL_SUITABILITY,
        QualityDimension.PERFORMANCE_EFFICIENCY,
        QualityDimension.COMPATIBILITY,
        QualityDimension.INTERACTION_CAPABILITY,
        QualityDimension.RELIABILITY,
        QualityDimension.SECURITY,
        QualityDimension.MAINTAINABILITY,
        QualityDimension.FLEXIBILITY,
        QualityDimension.SAFETY,
    }
    declared = {d.dimension for d in ISO25010_BASE.dimensions}
    assert declared == nine
    # And NOT the EVERSE-only additions.
    assert QualityDimension.FAIRNESS not in declared
    assert QualityDimension.REPRODUCIBILITY not in declared


def test_every_evaluator_resolves():
    for dim in ISO25010_BASE.dimensions:
        for ind in dim.indicators:
            assert resolve(ind.evaluator) is not None


def test_measured_and_skipped_split():
    # Security + Maintainability measure statically; the five out-of-scope
    # characteristics skip cleanly (not error).
    src = "def add(a, b):\n    return a + b\n"
    verdict = evaluate_profile(ISO25010_BASE, src, context={})
    by_dim = {d.dimension.value: d for d in verdict.dimensions}

    # Measured statically -> not skipped.
    assert by_dim["Security"].status.value in ("pass", "fail")
    assert by_dim["Maintainability"].status.value in ("pass", "fail")

    # Declared but not measured -> skipped, never error.
    for name in ("Performance Efficiency", "Compatibility",
                 "Interaction Capability", "Flexibility", "Safety"):
        assert by_dim[name].status.value == "skipped"


def test_functional_suitability_uses_verification_evaluators():
    fs = [d for d in ISO25010_BASE.dimensions
          if d.dimension is QualityDimension.FUNCTIONAL_SUITABILITY][0]
    evaluators = {i.evaluator for i in fs.indicators}
    # The distinctive QALLM contribution: execution-based verification maps
    # to 25010 Functional Suitability.
    assert "qallm.verification.pass_rate" in evaluators
    assert "qallm.verification.bugs" in evaluators
