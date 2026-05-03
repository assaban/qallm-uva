import shutil
import subprocess
from .base_analyzer import StaticCodeAnalyzer
from .analysis_model import RawToolResult
from qallm.ingestion.parsers import CodeUnit
from .normalization.base_normalizer import ToolNormalizer

class RuffAnalyzer(StaticCodeAnalyzer):
    """Linter and security strategy using Ruff."""

    def __init__(self):
        super().__init__()
        self.name = "ruff"
        # In a real setup, you'd implement a RuffNormalizer
        self.normalizer = None 

    def tool_name(self) -> str:
        return self.name

    def get_normalizer(self) -> ToolNormalizer:
        return self.normalizer

    def analyze(self, unit: CodeUnit) -> RawToolResult:
        if shutil.which("ruff") is None:
            return RawToolResult("ruff", 127, "", "ruff not installed")

        # Run ruff check on stdin[cite: 19]
        process = subprocess.run(
            ["ruff", "check", "--format", "json", "-"],
            input=unit.source,
            capture_output=True,
            text=True
        )

        return RawToolResult(
            tool=self.tool_name(),
            exit_code=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
            artifact=str(unit.original_path.absolute()) if unit.original_path else "cell.py"
        )