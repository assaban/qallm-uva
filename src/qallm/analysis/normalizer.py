from enum import Enum
from typing import Dict, Any


class LifecycleStage(Enum):
    INITIALIZATION = "initialization"
    IMPLEMENTATION = "implementation"
    PUBLICATION = "publication"


class LifecycleNormalizer:
    """Normalizes raw metrics based on the EOSC lifecycle."""

    # Example Thresholds for Maintainability Index (MI)
    THRESHOLDS = {
        LifecycleStage.INITIALIZATION: {"mi": 40.0, "cc": 15.0},
        LifecycleStage.IMPLEMENTATION: {"mi": 60.0, "cc": 10.0},
        LifecycleStage.PUBLICATION: {"mi": 80.0, "cc": 5.0},
    }

    def evaluate(self, metrics: Dict[str, Any], stage: LifecycleStage) -> str:
        mi = metrics.get("mi", 0)
        cc = metrics.get("cc", 99)

        limit = self.THRESHOLDS.get(stage)

        if mi >= limit["mi"] and cc <= limit["cc"]:
            return "PASSED"
        elif mi >= (limit["mi"] * 0.8):
            return "WARNING"
        return "REFINEMENT_REQUIRED"