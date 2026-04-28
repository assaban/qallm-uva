import pytest
from qallm.analysis.normalizer import LifecycleNormalizer, LifecycleStage

@pytest.fixture
def normalizer():
    return LifecycleNormalizer()

def test_initialization_stage_relaxed_thresholds(normalizer):
    """
    In Initialization, complexity is tolerated while prototyping [cite: 174-175].
    """
    raw_metrics = {"mi": 45.0, "cc": 12.0}
    status = normalizer.evaluate(raw_metrics, LifecycleStage.INITIALIZATION)
    assert status == "PASSED"

def test_publication_stage_strict_thresholds(normalizer):
    """
    In Publication, strict thresholds ensure reproducibility and quality [cite: 181-182].
    """
    # The same metrics that passed 'Initialization' should fail 'Publication'
    raw_metrics = {"mi": 45.0, "cc": 12.0}
    status = normalizer.evaluate(raw_metrics, LifecycleStage.PUBLICATION)
    assert status == "REFINEMENT_REQUIRED"

def test_implementation_warning_state(normalizer):
    """
    Implementation phase provides a 'WARNING' buffer for moderate issues [cite: 178-180].
    """
    # MI of 50 is 83% of the Implementation threshold (60)
    raw_metrics = {"mi": 50.0, "cc": 9.0}
    status = normalizer.evaluate(raw_metrics, LifecycleStage.IMPLEMENTATION)
    assert status == "WARNING"