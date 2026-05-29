"""Tests for the FAIR4RS publication-stage quality profile.

The point of a second profile is to prove the selector and profile
machinery generalise beyond one framework. These tests assert FAIR4RS is
real (every evaluator resolves and the profile runs to a verdict), not a
stub.
"""

from qallm.evaluation import evaluate_profile, resolve
from qallm.profiles import (
    FAIR4RS_PUBLICATION,
    LifecycleStage,
    get_profile,
    list_profiles,
)


def test_fair4rs_is_registered():
    assert "fair4rs_publication" in list_profiles()
    assert get_profile("fair4rs_publication") is FAIR4RS_PUBLICATION


def test_fair4rs_targets_publication_stage():
    assert FAIR4RS_PUBLICATION.lifecycle_stage is LifecycleStage.PUBLICATION


def test_fair4rs_every_evaluator_resolves():
    # If any indicator named an unregistered evaluator, the profile would
    # be a stub that crashes at run time. Resolve them all up front.
    for dim in FAIR4RS_PUBLICATION.dimensions:
        for ind in dim.indicators:
            assert resolve(ind.evaluator) is not None


def test_fair4rs_runs_to_a_verdict():
    # A source with docstrings but no project files should yield a real
    # verdict: docstring_coverage measured, project-file probes SKIPPED.
    src = (
        'def add(a, b):\n'
        '    """Return the sum."""\n'
        '    return a + b\n'
    )
    verdict = evaluate_profile(FAIR4RS_PUBLICATION, src, context={})
    dims = {d.dimension.value: d for d in verdict.dimensions}
    assert "FAIRness" in dims
    cov = [i for i in dims["FAIRness"].indicators if i.name == "docstring_coverage"][0]
    assert cov.measured is not None  # actually computed, not skipped
