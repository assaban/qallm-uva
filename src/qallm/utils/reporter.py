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

    def generate_comparison_script(self):
        """Generates a script to run generated tests against both original and repaired code."""
        script_path = self.report_dir / "run_benchmarks.py"

        script_content = """
    import subprocess
    from pathlib import Path
    import shutil
    import json
    import os

    # Configuration based on QALLM report structure[cite: 42]
    REPAIRS_DIR = Path("./repairs")
    TESTS_DIR = Path("./generated_tests")
    RESULTS_DIR = Path("./benchmark_results")
    RESULTS_DIR.mkdir(exist_ok=True)

    def run_test_suite(code_file: Path, label: str):
        print(f"\\n>>> Testing {label.upper()} version: {code_file.name}")

        # Setup: Rename target to the expected module name[cite: 36]
        # This ensures "from source_domain_c0 import ..." works in the test files[cite: 37]
        target_module = Path("source_domain_c0.py")
        shutil.copy(code_file, target_module)

        # FIX: Force pytest to discover files with our specific naming convention
        cmd = [
            "pytest",
            "-o", "python_files=*_round_*.py", 
            str(TESTS_DIR),
            "--json-report",
            f"--json-report-file={RESULTS_DIR}/results_{label}.json",
            "-q", "--no-header"
        ]

        subprocess.run(cmd)

        if target_module.exists():
            target_module.unlink()

    def summarize_results():
        print("\\n" + "="*50)
        print("FINAL QUALITY BENCHMARK SUMMARY")
        print("="*50)

        for label in ["original", "repaired"]:
            json_path = RESULTS_DIR / f"results_{label}.json"
            if not json_path.exists():
                continue

            with open(json_path) as f:
                data = json.load(f)
                summary = data.get("summary", {})
                passed = summary.get("passed", 0)
                failed = summary.get("failed", 0)
                total = summary.get("total", 0)

                # Identify crash bugs (Oracle: crash)[cite: 45]
                # In our RL loop, failures represent identified vulnerabilities
                status = "✅ STABLE" if failed == 0 and total > 0 else f"❌ {failed} CRASHES FOUND"

                print(f"{label.upper():<10}: {status} ({passed}/{total} tests passed)")

    if __name__ == "__main__":
        # 1. Run against Original[cite: 47]
        orig = list(REPAIRS_DIR.glob("*_original.py"))
        if orig:
            run_test_suite(orig[0], "original")

        # 2. Run against Repaired[cite: 47]
        repaired = list(REPAIRS_DIR.glob("*_repaired.py"))
        if repaired:
            run_test_suite(repaired[0], "repaired")

        summarize_results()
    """
        script_path.write_text(script_content.strip(), encoding="utf-8")
        return script_path