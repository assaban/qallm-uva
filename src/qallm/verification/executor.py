"""Test executor: runs generated pytest code in an isolated subprocess.

Creates a temporary directory with the source file and generated test,
then runs pytest with coverage.py. DependencyMapper copies sibling
modules so that the target code's own imports resolve.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from qallm.verification.models import ExecutionResult, TestDetail
from qallm.verification.sandbox import DependencyMapper

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 60


def _parse_pytest_json(report_path: Path) -> tuple[list[TestDetail], dict[str, int]]:
    if not report_path.exists():
        return [], {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot parse pytest JSON report: %s", exc)
        return [], {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}

    details: list[TestDetail] = []
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}

    for test in data.get("tests", []):
        outcome = test.get("outcome", "error")
        status = {"passed": "passed", "failed": "failed", "skipped": "skipped"}.get(outcome, "error")
        counts[status] = counts.get(status, 0) + 1

        message = None
        call_info = test.get("call", {})
        if call_info and call_info.get("longrepr"):
            # Keep enough of the traceback for the detailed assertion diff
            # (-v / --tb=long), not just the one-line summary.
            message = str(call_info["longrepr"])[:2000]

        details.append(TestDetail(
            name=test.get("nodeid", "unknown"), status=status,
            message=message,
            duration_seconds=call_info.get("duration", 0.0) if call_info else 0.0,
        ))

    return details, counts


def _parse_coverage_json(coverage_path: Path) -> tuple[float | None, dict[str, float]]:
    if not coverage_path.exists():
        return None, {}
    try:
        data = json.loads(coverage_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot parse coverage JSON report: %s", exc)
        return None, {}

    totals = data.get("totals", {})
    overall = totals.get("percent_covered")
    per_file: dict[str, float] = {}
    for filepath, file_data in data.get("files", {}).items():
        summary = file_data.get("summary", {})
        pct = summary.get("percent_covered")
        if pct is not None:
            per_file[filepath] = pct

    return overall, per_file


def run_tests(
    source_code: str,
    test_code: str,
    source_filename: str = "source_module.py",
    source_origin: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> ExecutionResult:
    """Execute generated tests against source code in an isolated subprocess.

    Args:
        source_code: Python source code of the module under test.
        test_code: Generated pytest test code.
        source_filename: Filename for the source module.
        source_origin: Original file path (used by DependencyMapper to find siblings).
        timeout: Maximum wall-clock seconds.
    """
    work_dir = Path(tempfile.mkdtemp(prefix="qallm_test_"))
    module_name = source_filename.removesuffix(".py")
    logger.info(f"Run test for {source_origin}::{module_name}!")
    try:
        source_path = work_dir / source_filename
        source_path.write_text(source_code, encoding="utf-8")

        # Sibling-import resolution. If the target uses ``from foo import ...``
        # to reach a sibling module or package, those imports must be
        # satisfiable inside the sandbox. DependencyMapper copies the
        # relevant tree; if it cannot (no source_origin, missing file,
        # or unrecognised structure), tests that exercise those imports
        # will fail with ModuleNotFoundError. We log loudly so the user
        # can see why.
        if source_origin and source_origin.exists():
            copied = DependencyMapper.resolve_and_copy(source_origin, work_dir)
            if copied:
                logger.info(
                    "Sandbox dependency resolution: copied %s into %s",
                    ", ".join(copied), work_dir,
                )
        else:
            logger.warning(
                "Sandbox dependency resolution skipped: source_origin=%s "
                "(exists=%s). Tests that import from sibling modules will fail.",
                source_origin,
                source_origin.exists() if source_origin else False,
            )

        test_path = work_dir / "test_generated.py"

        # test_path.write_text(test_code, encoding="utf-8")
        header = f"from {module_name} import *\n\n"
        test_path.write_text(header + test_code, encoding="utf-8")

        json_report_path = work_dir / "report.json"
        coverage_json_path = work_dir / "coverage.json"

        cmd = [
            "python", "-m", "pytest", str(test_path),
            "--json-report", f"--json-report-file={json_report_path}",
            f"--cov={module_name}", "--cov-branch",
            f"--cov-report=json:{coverage_json_path}",
            # -v and a long traceback give the detailed assertion diff the
            # user needs to understand *why* a test failed (e.g. the full
            # "At index 1 diff" breakdown), not just the one-line summary.
            "--cov-report=", "--no-header", "--tb=long", "-v",
        ]

        logger.debug("Executing tests in %s (timeout=%ds)", work_dir, timeout)
        logger.debug("Executing command: %s", " ".join(cmd))
        start = time.monotonic()

        proc = subprocess.run(
            cmd, cwd=str(work_dir), capture_output=True, text=True, timeout=timeout,
        )

        duration = time.monotonic() - start
        test_details, counts = _parse_pytest_json(json_report_path)
        coverage_pct, coverage_branches = _parse_coverage_json(coverage_json_path)
        total = counts["passed"] + counts["failed"] + counts["errors"] + counts["skipped"]

        logger.info(f"Test execution: {source_origin}:{str(test_path)} completed!")
        return ExecutionResult(
            passed=counts["passed"], failed=counts["failed"],
            errors=counts["errors"], skipped=counts["skipped"],
            total=total, coverage_percent=coverage_pct,
            coverage_branches=coverage_branches,
            duration_seconds=round(duration, 3),
            test_details=test_details,
            stdout=proc.stdout[:2000] if proc.stdout else "",
            stderr=proc.stderr[:2000] if proc.stderr else "",
        )

    except subprocess.TimeoutExpired:
        logger.warning("Test execution timed out after %ds", timeout)
        return ExecutionResult(execution_error=f"Timeout after {timeout} seconds",
                               duration_seconds=float(timeout))
    except Exception as exc:
        logger.error("Test execution failed: %s", exc)
        return ExecutionResult(execution_error=str(exc))
    finally:
        try:
            shutil.rmtree(work_dir)
        except OSError:
            logger.warning("Could not remove temp dir: %s", work_dir)
