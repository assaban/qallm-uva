from __future__ import annotations
import shutil
import subprocess
import json
import re

from .base_analyzer import StaticCodeAnalyzer
from .analysis_model import RawToolResult
from qallm.ingestion.parsers import CodeUnit
from .normalization.base_normalizer import ToolNormalizer
from .normalization.bandit_normalizer import BanditNormalizer


class BanditAnalyzer(StaticCodeAnalyzer):
    """Security analysis strategy using Bandit."""

    def __init__(self):
        super().__init__()
        self.name = "bandit"
        self.normalizer = BanditNormalizer()

    def tool_name(self) -> str:
        return self.name

    def get_normalizer(self) -> ToolNormalizer:
        return self.normalizer

    def _safe_parse(self, stdout: str) -> dict:
        """Robustly extracts JSON from stdout, stripping ANSI sequences."""
        if not stdout:
            return {}

        # Strip ANSI escape sequences (terminal colors)
        clean_text = re.sub(r'\x1b\[[0-9;]*[mGKF]', '', stdout).strip()

        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            # Fallback: Find the first '{' and last '}'
            start = clean_text.find('{')
            end = clean_text.rfind('}')
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(clean_text[start:end + 1])
                except json.JSONDecodeError:
                    pass
            return {}

    def analyze(self, unit: CodeUnit) -> RawToolResult:
        if shutil.which("bandit") is None:
            return RawToolResult("bandit", 127, "", "bandit not installed")

        # Run bandit on stdin to analyze the CodeUnit source directly
        process = subprocess.run(
            ["bandit", "-r", "-f", "json", "-q", "-"],
            input=unit.source,
            capture_output=True,
            text=True
        )

        # Use robust parsing
        bandit_json = self._safe_parse(process.stdout)

        return RawToolResult(
            tool=self.tool_name(),
            exit_code=process.returncode,
            stdout=json.dumps(bandit_json),
            stderr=process.stderr,
            # Point to the original file path for snippet extraction
            artifact=str(unit.original_path.absolute()) if unit.original_path else "cell.py"
        )