import pytest
from qallm.stage2_lre.verifier import VerificationRunner


def test_runner_detects_passing_code():
    runner = VerificationRunner()
    target = "def add(a, b): return a + b"
    test = "def test_add(): assert add(1, 2) == 3"

    result = runner.run_test(test, target)
    assert result.success is True


def test_runner_detects_bug():
    runner = VerificationRunner()
    target = "def add(a, b): return a - b"  # Logical bug
    test = "def test_add(): assert add(1, 1) == 2"

    result = runner.run_test(test, target)
    assert result.success is False
    assert not result.is_broken_test


def test_runner_detects_broken_test():
    runner = VerificationRunner()
    target = "x = 1"
    test = "def test_fail(): syntax error here !!!"

    result = runner.run_test(test, target)
    assert result.is_broken_test is True