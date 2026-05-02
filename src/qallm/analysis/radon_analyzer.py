from __future__ import annotations
import shutil
import subprocess
import json
import re

from .base_analyzer import StaticCodeAnalyzer
from .analysis_model import RawToolResult
from qallm.ingestion.parsers import CodeUnit
from .normalization.base_normalizer import ToolNormalizer
from .normalization.radon_normalizer import RadonNormalizer


class RadonAnalyzer(StaticCodeAnalyzer):
    """Complexity and Maintainability analysis strategy using Radon."""

    def __init__(self):
        super().__init__()
        self.name = "Radon"
        self.normalizer = RadonNormalizer()

    def tool_name(self) -> str:
        return self.name

    def get_normalizer(self) -> ToolNormalizer:
        return self.normalizer

    def _safe_parse(self, stdout: str) -> dict:
        """
        Robustly extracts JSON from stdout by stripping ANSI sequences
        and isolating the first valid JSON object.
        """
        if not stdout:
            return {}

        # 1. Remove ANSI escape sequences (like \x1b[0m or [0m)
        # This handles the terminal color codes often found in local execution
        clean_text = re.sub(r'\x1b\[[0-9;]*[mGKF]', '', stdout)

        # 2. Basic cleanup of surrounding whitespace/newlines
        clean_text = clean_text.strip()

        if not clean_text:
            return {}

        try:
            # Try direct parse first
            return json.loads(clean_text)
        except json.JSONDecodeError:
            # 3. If direct parse fails, find the first '{' and last '}'
            # This bypasses "Extra data" errors caused by trailing log messages
            start = clean_text.find('{')
            end = clean_text.rfind('}')

            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(clean_text[start:end + 1])
                except json.JSONDecodeError:
                    pass
            return {}

    def analyze(self, unit: CodeUnit) -> RawToolResult:
        if shutil.which("radon") is None:
            return RawToolResult("radon", 127, "", "radon not installed")

        # 1. Run Cyclomatic Complexity (CC)
        res_cc = subprocess.run(
            ["radon", "cc", "-", "-j"],
            input=unit.source,
            capture_output=True,
            text=True
        )

        # 2. Run Maintainability Index (MI)
        res_mi = subprocess.run(
            ["radon", "mi", "-", "-j"],
            input=unit.source,
            capture_output=True,
            text=True
        )

        # Use robust parsing to get data from both outputs
        cc_json = self._safe_parse(res_cc.stdout)
        mi_json = self._safe_parse(res_mi.stdout)

        # Radon keys by "-" or "<stdin>" when reading from a pipe
        # The logic below handles both possibilities
        combined_data = {
            "complexity": cc_json.get("-", cc_json.get("<stdin>", [])),
            "maintainability": mi_json.get("-", mi_json.get("<stdin>", {}))
        }

        return RawToolResult(
            tool=self.tool_name(),
            exit_code=0 if (res_cc.returncode == 0 and res_mi.returncode == 0) else 1,
            stdout=json.dumps(combined_data),
            stderr=res_cc.stderr + res_mi.stderr,
            # Pass file name for report clarity
            artifact=str(unit.original_path.absolute()) if unit.original_path else "cell.py"
        )