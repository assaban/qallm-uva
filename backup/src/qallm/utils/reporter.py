import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


class QualityReporter:
    """Handles persistence of analysis and verification data for thesis auditability."""

    def __init__(self, base_dir: str = "outputs/reports"):
        # Creates a unique folder for the current run
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.report_dir = Path(base_dir) / self.run_id
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def save_static_report(self, data: List[Dict[str, Any]]) -> Path:
        """Saves the raw JSON from the StaticAnalyzer."""
        report_path = self.report_dir / "static_analysis.json"
        with open(report_path, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return report_path

    def save_summary_md(self, summary_text: str) -> Path:
        """Saves a human-readable summary of the findings."""
        summary_path = self.report_dir / "summary.md"
        with open(summary_path, "w", encoding='utf-8') as f:
            f.write(summary_text)
        return summary_path