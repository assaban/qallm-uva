import json
import os
from pathlib import Path
from dataclasses import asdict, is_dataclass
from typing import Any
from datetime import datetime


class QualityReporter:
    """Handles persistence of analysis results and verification logs."""

    def __init__(self, base_dir: str = "outputs/reports"):

        # Creates a unique folder for the current run
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.report_dir = Path(base_dir) / self.run_id
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def _json_serialize(self, obj: Any) -> Any:
        """Helper to convert dataclasses to dicts for JSON serialization."""
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, (set, Path)):
            return str(obj)
        raise TypeError(f"Type {type(obj)} not serializable")

    def save_static_report(self, reports: list):
        """Saves unified finding objects to disk."""
        path = self.report_dir / "static_analysis.json"
        with open(path, "w", encoding="utf-8") as f:
            # We use the default parameter to catch any non-serializable objects
            json.dump(reports, f, indent=4, default=self._json_serialize)