"""Tests for the test executor (subprocess sandbox with coverage)."""
from qallm.verification.executor import run_tests


def test_passing_test_detected():
    source = "def add(a, b): return a + b"
    test = "from source_module import add\ndef test_add(): assert add(1, 2) == 3"
    result = run_tests(source, test)
    assert result.passed >= 1
    assert result.failed == 0


def test_failing_test_finds_bug():
    source = "def add(a, b): return a - b"  # Logical bug
    test = "from source_module import add\ndef test_add(): assert add(1, 1) == 2"
    result = run_tests(source, test)
    assert result.failed >= 1
    assert result.bugs_found >= 1


def test_coverage_is_measured():
    source = "def double(x): return x * 2"
    test = "from source_module import double\ndef test_double(): assert double(3) == 6"
    result = run_tests(source, test)
    assert result.coverage_percent is not None
    assert result.coverage_percent > 0


def test_timeout_handled():
    source = "import time\ndef slow(): time.sleep(100)"
    test = "from source_module import slow\ndef test_slow(): slow()"
    result = run_tests(source, test, timeout=2)
    assert result.execution_error is not None
    assert "Timeout" in result.execution_error
