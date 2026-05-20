"""Tests for qallm.profiles.

Profiles is a pure declarative module: enums, dataclasses, lookups. The
tests stay narrow on purpose. They verify:

  * The four EVERSE dimensions QALLM commits to in v1 are present.
  * The default profile covers all four with at least one indicator each.
  * Threshold comparison passes and fails correctly for each comparator.
  * Profiles roundtrip to a JSON-friendly dict.
  * Lookup helpers behave predictably for known and unknown ids.
"""

from __future__ import annotations

import json

import pytest

from qallm.profiles import (
    IMPLEMENTATION_DEFAULT,
    Comparator,
    DimensionSpec,
    LifecycleStage,
    QualityDimension,
    QualityIndicator,
    QualityProfile,
    default_profile_for,
    get_profile,
    list_profiles,
)


# ---------------------------------------------------------------------------
# Dimensions and the default profile
# ---------------------------------------------------------------------------


def test_default_profile_covers_the_four_v1_dimensions():
    expected = {
        QualityDimension.MAINTAINABILITY,
        QualityDimension.SECURITY,
        QualityDimension.RELIABILITY,
        QualityDimension.REPRODUCIBILITY,
    }
    actual = {spec.dimension for spec in IMPLEMENTATION_DEFAULT.dimensions}
    assert actual == expected


def test_default_profile_has_at_least_one_indicator_per_dimension():
    for spec in IMPLEMENTATION_DEFAULT.dimensions:
        assert len(spec.indicators) >= 1, (
            f"Dimension {spec.dimension} has no indicators"
        )


def test_default_profile_targets_implementation_stage():
    assert IMPLEMENTATION_DEFAULT.lifecycle_stage is LifecycleStage.IMPLEMENTATION


def test_indicator_names_are_unique_within_default_profile():
    names = IMPLEMENTATION_DEFAULT.indicator_names()
    assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# Comparator semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "comparator,measured,threshold,expected",
    [
        (Comparator.GE, 70.0, 60.0, True),
        (Comparator.GE, 50.0, 60.0, False),
        (Comparator.GE, 60.0, 60.0, True),
        (Comparator.LE, 8.0, 10.0, True),
        (Comparator.LE, 12.0, 10.0, False),
        (Comparator.LE, 10.0, 10.0, True),
        (Comparator.EQ, 1.0, 1.0, True),
        (Comparator.EQ, 1.0, 0.0, False),
    ],
)
def test_comparator_passes_evaluates_correctly(
    comparator: Comparator, measured: float, threshold: float, expected: bool
):
    assert comparator.passes(measured, threshold) is expected


def test_indicator_passes_uses_its_comparator():
    mi = QualityIndicator(
        name="mi",
        evaluator="radon.mi",
        threshold=60.0,
        comparator=Comparator.GE,
    )
    assert mi.passes(70.0) is True
    assert mi.passes(50.0) is False


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def test_get_profile_returns_known_profile():
    p = get_profile("implementation_default")
    assert p is IMPLEMENTATION_DEFAULT


def test_get_profile_raises_on_unknown_id_with_helpful_message():
    with pytest.raises(KeyError) as info:
        get_profile("does_not_exist")
    assert "implementation_default" in str(info.value)


def test_list_profiles_includes_default():
    assert "implementation_default" in list_profiles()


def test_default_profile_for_stage_returns_implementation_default_for_impl():
    p = default_profile_for(LifecycleStage.IMPLEMENTATION)
    assert p is IMPLEMENTATION_DEFAULT


def test_default_profile_for_unregistered_stage_falls_back_to_implementation():
    # v1 only registers an implementation-stage default; other stages should
    # still get a usable profile rather than raising.
    p = default_profile_for(LifecycleStage.PUBLICATION)
    assert isinstance(p, QualityProfile)


# ---------------------------------------------------------------------------
# Membership helpers on the profile
# ---------------------------------------------------------------------------


def test_profile_covers_known_dimension():
    assert IMPLEMENTATION_DEFAULT.covers(QualityDimension.RELIABILITY) is True


def test_get_dimension_returns_spec_for_present_dimension():
    spec = IMPLEMENTATION_DEFAULT.get_dimension(QualityDimension.MAINTAINABILITY)
    assert isinstance(spec, DimensionSpec)
    assert spec.dimension is QualityDimension.MAINTAINABILITY


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def test_profile_roundtrips_through_json():
    payload = IMPLEMENTATION_DEFAULT.to_dict()
    text = json.dumps(payload)  # must be JSON-serialisable
    loaded = json.loads(text)
    assert loaded["profile_id"] == "implementation_default"
    assert loaded["lifecycle_stage"] == "implementation"
    dims = [d["dimension"] for d in loaded["dimensions"]]
    assert set(dims) == {
        "Maintainability",
        "Security",
        "Reliability",
        "Reproducibility",
    }


def test_indicator_dict_uses_string_comparator():
    ind = QualityIndicator(
        name="example",
        evaluator="dummy",
        threshold=1.0,
        comparator=Comparator.GE,
    )
    data = ind.to_dict()
    assert data["comparator"] == "ge"
