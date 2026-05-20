import json
from pathlib import Path
from dataclasses import asdict, is_dataclass
from typing import Any
from datetime import datetime

from qallm.analysis.analysis_model import AnalysedCodeUnit
from qallm.repair.repair_model import RepairedCodeUnit
from qallm.verification.models import TestedCodeUnit, TestGenerationSession


def _json_serialize(obj: Any) -> Any:
    """Helper to convert dataclasses to dicts for JSON serialization."""
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, (set, Path)):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


class QualityReporter:
    """Handles persistence of analysis results and verification logs."""

    def __init__(self, base_dir: str = "outputs/reports", run_id: str = None):

        # Creates a unique folder for the current run
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.report_dir = Path(base_dir) / self.run_id
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def save_static_report(self, analysed_code_unit: AnalysedCodeUnit, round_suffix:str) -> None:
        """Saves unified finding objects to disk."""
        round_suffix = self.report_dir / f"{round_suffix}"
        round_suffix.mkdir(parents=True, exist_ok=True)

        filename = analysed_code_unit.code_unit.original_path.name
        if filename.endswith(".py"):
            filename = filename.replace(".py", "_static_analysis.json")
        path = round_suffix / f"{filename}"

        with open(path, "w", encoding="utf-8") as f:
            # We use the default parameter to catch any non-serializable objects
            json.dump(analysed_code_unit.findings, f, indent=4, default=_json_serialize)

    def save_static_repair_artifacts(self, repaired_code_unit: RepairedCodeUnit, round_suffix:str) -> None:
        """Save original, repaired, and diff files for audit trail."""
        repairs_dir = self.report_dir / f"{round_suffix}/repairs"
        repairs_dir.mkdir(parents=True, exist_ok=True)

        filename = repaired_code_unit.original_code_unit.original_path.stem
        fromfile = f"{filename}_original.py"
        tofile = f"{filename}_repaired.py"

        (repairs_dir / Path(fromfile).name).write_text(repaired_code_unit.original_code_unit.source_code, encoding="utf-8")
        (repairs_dir / Path(tofile).name).write_text(repaired_code_unit.repaired_result.repaired_source, encoding="utf-8")

        if repaired_code_unit.repaired_result.unified_diff:
            (repairs_dir / f"{filename}.diff").write_text(repaired_code_unit.repaired_result.unified_diff, encoding="utf-8")

        # Save repair metadata
        meta = {
            "raw_file": repaired_code_unit.original_code_unit.original_path.name,
            "from_file": fromfile,
            "repaired_file": tofile,
            "compiles": repaired_code_unit.repaired_result.compiles,
            "validation_error": repaired_code_unit.repaired_result.validation_error,
            "explanation": repaired_code_unit.repaired_result.explanation,
        }
        (repairs_dir / f"{filename}_meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )

    def save_verification_artifacts(self, tested_unit: TestedCodeUnit, round_suffix: str):
        """Handles all persistence for the verification stage."""
        round_dir = self.report_dir / round_suffix
        tests_dir = round_dir / "generated_tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        filename = tested_unit.repaired_unit.original_code_unit.original_path.stem
        for session in tested_unit.sessions:
            # 1. Save the latest Python test file[cite: 28]
            if session.rounds:
                last_round = session.rounds[-1]
                if last_round.generated_test.is_valid:
                    method_filename = f"test_{filename}_{session.function_name}.py"
                    (tests_dir / method_filename).write_text(last_round.generated_test.test_code)

            # 2. Save the full Session JSON for the function[cite: 28]
            self._save_session(session, tests_dir / f"test_{session.function_name}_result.json")

    @staticmethod
    def _save_session(session: TestGenerationSession, output_path: Path) -> None:
        """Persist a verification session as JSON for reproducibility.

        Includes computed properties (final_coverage, final_bugs, learning_curve)
        which are @property methods not captured by dataclasses.asdict().
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(session)
        # Inject computed properties that asdict() skips
        data["final_coverage"] = session.final_coverage
        data["final_bugs"] = session.final_bugs
        data["learning_curve"] = session.learning_curve
        data["reward_per_round"] = session.reward_per_round
        output_path.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )

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