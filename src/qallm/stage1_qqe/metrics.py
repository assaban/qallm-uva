import subprocess
import json
from typing import List, Dict, Any
from qallm.ingestion.parsers import CodeUnit

class StaticAnalyzer:
    """Stage 2: Static Quality Analysis Agent[cite: 75, 90]."""

    def analyze(self, units: List[CodeUnit]) -> List[Dict[str, Any]]:
        """Orchestrates static analysis across a batch of code units[cite: 77]."""
        return [self._analyze_single_unit(u) for u in units]

    def _analyze_single_unit(self, unit: CodeUnit) -> Dict[str, Any]:
        """Runs the P4 static analysis tools (Radon, Bandit)[cite: 66, 68]."""
        report = {
            "cell_index": unit.cell_index,
            "metrics": {},
            "issues": []
        }

        # 1. Maintainability Index (MI) - Robust Parser [cite: 68, 93]
        res_mi = subprocess.run(
            ["radon", "mi", "-j", "-"],
            input=unit.source, capture_output=True, text=True
        )
        if res_mi.returncode == 0 and res_mi.stdout.strip():
            try:
                data = json.loads(res_mi.stdout)
                # Radon MI output can be {"<stdin>": 100.0} or {"<stdin>": {"mi": 100.0}}
                for val in data.values():
                    if isinstance(val, (int, float)):
                        report["metrics"]["mi"] = val
                        break
                    if isinstance(val, dict) and "mi" in val:
                        report["metrics"]["mi"] = val["mi"]
                        break
            except json.JSONDecodeError:
                pass

        # 2. Cyclomatic Complexity (CC) - Robust Parser [cite: 68, 93]
        res_cc = subprocess.run(
            ["radon", "cc", "-j", "-"],
            input=unit.source, capture_output=True, text=True
        )
        if res_cc.returncode == 0 and res_cc.stdout.strip():
            try:
                data = json.loads(res_cc.stdout)
                # CC usually returns a list of blocks per file key
                for blocks in data.values():
                    if isinstance(blocks, list) and len(blocks) > 0:
                        avg_cc = sum(b.get("complexity", 0) for b in blocks) / len(blocks)
                        report["metrics"]["cc"] = avg_cc
                        break
            except (json.JSONDecodeError, ZeroDivisionError):
                pass

        # 3. Security Vulnerabilities (Bandit) [cite: 68, 92]
        res_sec = subprocess.run(
            ["bandit", "-r", "-f", "json", "-q", "-"],
            input=unit.source, capture_output=True, text=True
        )
        if res_sec.stdout.strip():
            try:
                data = json.loads(res_sec.stdout)
                report["issues"].extend(data.get("results", []))
            except json.JSONDecodeError:
                pass

        return report