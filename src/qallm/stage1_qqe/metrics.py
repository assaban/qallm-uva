import subprocess
import json
from qallm.ingestion.parsers import CodeUnit

class StaticAnalyzer:
    """Stage 2: Structural Analysis Agent with mandatory audit metadata."""

    def analyze(self, units: list):
        """Orchestrates static analysis across a batch of code units."""
        return [self._analyze_single_unit(u) for u in units]

    def _analyze_single_unit(self, unit: CodeUnit):
        """Runs Radon and Bandit and captures file metadata for the final JSON."""
        report = {
            "file_name": unit.original_path.name,
            "full_path": str(unit.original_path),
            "cell_index": unit.cell_index,
            "metrics": {"mi": 0.0, "cc": 0.0},
            "issues": []
        }

        # 1. Maintainability Index (Radon)
        res_mi = subprocess.run(["radon", "mi", "-j", "-"], input=unit.source, capture_output=True, text=True)
        if res_mi.returncode == 0 and res_mi.stdout.strip():
            try:
                data = json.loads(res_mi.stdout)
                val = list(data.values())[0]
                report["metrics"]["mi"] = val.get("mi") if isinstance(val, dict) else val
            except: pass

        # 2. Cyclomatic Complexity (Radon)
        res_cc = subprocess.run(["radon", "cc", "-j", "-"], input=unit.source, capture_output=True, text=True)
        if res_cc.returncode == 0 and res_cc.stdout.strip():
            try:
                data = json.loads(res_cc.stdout)
                blocks = list(data.values())[0]
                if blocks:
                    report["metrics"]["cc"] = sum(b.get("complexity", 0) for b in blocks) / len(blocks)
            except: pass

        # 3. Security (Bandit)
        res_sec = subprocess.run(["bandit", "-r", "-f", "json", "-q", "-"], input=unit.source, capture_output=True, text=True)
        if res_sec.stdout.strip():
            try:
                data = json.loads(res_sec.stdout)
                report["issues"].extend(data.get("results", []))
            except: pass

        return report