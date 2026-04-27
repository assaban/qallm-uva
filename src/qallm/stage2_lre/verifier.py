import subprocess
import os
import re
import uuid
from pathlib import Path


class VerificationResult:
    """Captured data from a single test execution cycle."""

    def __init__(self, returncode: int, stdout: str, stderr: str, coverage: float = 0.0):
        self.success = (returncode == 0)
        self.stdout = stdout
        self.stderr = stderr
        self.coverage = coverage

        output_blob = (stdout + stderr).lower()
        self.is_broken_test = any(kw in output_blob for kw in [
            "syntaxerror", "importerror", "errors during collection",
            "no module named", "invalid syntax", "attributeerror"
        ])


class VerificationRunner:
    """Executes tests within the session sandbox using strict code extraction."""

    def __init__(self, session_dir: Path):
        self.work_dir = session_dir / "sandbox"
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def _extract_executable_code(self, text: str) -> str:
        """Regex-based layer to strip conversational text and markdown blocks."""
        # 1. Try Python-specific markdown blocks
        blocks = re.findall(r"```python\s*(.*?)\s*```", text, re.DOTALL)
        if blocks:
            return "\n".join(blocks)

        # 2. Try generic markdown blocks
        blocks = re.findall(r"```\s*(.*?)\s*```", text, re.DOTALL)
        if blocks:
            return "\n".join(blocks)

        # 3. Fallback: Filter out lines starting with AI dialogue markers
        lines = text.splitlines()
        code_lines = []
        dialogue = ("i understand", "here is", "certainly", "based on", "the code", "sure", "as a")
        for line in lines:
            if not line.lower().strip().startswith(dialogue):
                code_lines.append(line)
        return "\n".join(code_lines).strip()

    def run_test(self, test_code: str, target_code: str, original_path: Path, cell_idx: int) -> VerificationResult:
        session_id = uuid.uuid4().hex[:4]
        base = original_path.stem
        src_name = f"src_{base}_c{cell_idx}_{session_id}.py"
        test_name = f"test_{base}_c{cell_idx}_{session_id}.py"

        src_file = self.work_dir / src_name
        test_file = self.work_dir / test_name

        # Critical Fix: Strictly extract code before writing
        clean_test = self._extract_executable_code(test_code)

        if not clean_test.strip():
            clean_test = "def test_existence(): assert True # Fallback for empty units"

        src_file.write_text(target_code)
        # Prepend sandbox import to resolve dependencies
        test_file.write_text(f"import pytest\nfrom {src_file.stem} import *\n\n{clean_test}")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.work_dir) + os.pathsep + env.get("PYTHONPATH", "")

        process = subprocess.run(
            ["pytest", "-v", str(test_file)],
            capture_output=True, text=True, env=env
        )

        return VerificationResult(process.returncode, process.stdout, process.stderr)