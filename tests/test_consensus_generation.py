"""Tests for multi-sample consensus test generation and oracle threading."""

from unittest.mock import MagicMock, patch

from qallm.verification.generator import TestGenerator
from qallm.verification.models import GeneratedTest, FunctionInfo


def _suite(test_code, valid=True):
    return GeneratedTest(
        function_name="f", oracle="correctness", test_code=test_code,
        is_valid=valid, generation_error=None, model="m", provider="p",
        input_tokens=10, output_tokens=20, discarded_tests=[],
    )


def _fi():
    return FunctionInfo(name="f", source="def f(x):\n    return x",
                        docstring="d", args=[("x", None)], lineno=1, filepath="x.py")


def test_merge_unions_tests_from_samples_without_collision():
    gen = TestGenerator(llm=MagicMock())
    s1 = _suite("import pytest\nfrom source_module import f\n\ndef test_a():\n    assert f(1) == 2\n")
    s2 = _suite("import pytest\nfrom source_module import f\n\ndef test_a():\n    assert f(3) == 4\n")
    merged = gen._merge_samples([s1, s2], _fi(), "correctness", "source_module")
    assert merged.is_valid
    # Both samples' tests survive, namespaced so they do not collide.
    assert "def test_a_s0" in merged.test_code
    assert "def test_a_s1" in merged.test_code
    assert "assert f(1) == 2" in merged.test_code
    assert "assert f(3) == 4" in merged.test_code
    # Import appears once.
    assert merged.test_code.count("from source_module import f") == 1


def test_merge_sums_tokens_and_discards():
    gen = TestGenerator(llm=MagicMock())
    s1 = _suite("from source_module import f\n\ndef test_a():\n    assert f(1) == 1\n")
    s2 = _suite("from source_module import f\n\ndef test_b():\n    assert f(2) == 2\n")
    merged = gen._merge_samples([s1, s2], _fi(), "correctness", "source_module")
    assert merged.input_tokens == 20
    assert merged.output_tokens == 40


def test_merge_returns_first_when_none_valid():
    gen = TestGenerator(llm=MagicMock())
    s1 = _suite("", valid=False)
    s2 = _suite("", valid=False)
    merged = gen._merge_samples([s1, s2], _fi(), "correctness", "source_module")
    assert merged is s1


def test_samples_one_calls_generate_once_directly():
    gen = TestGenerator(llm=MagicMock())
    with patch.object(gen, "_generate_once", return_value=_suite("x")) as once:
        gen.generate(_fi(), oracle="correctness", samples=1)
        assert once.call_count == 1


def test_samples_three_calls_generate_once_three_times():
    gen = TestGenerator(llm=MagicMock())
    with patch.object(gen, "_generate_once", return_value=_suite(
        "from source_module import f\n\ndef test_a():\n    assert f(1) == 1\n"
    )) as once:
        gen.generate(_fi(), oracle="correctness", samples=3, module_name="source_module")
        assert once.call_count == 3


def test_feedback_round_ignores_samples():
    """Feedback rounds (existing_session) refine one suite, so a single sample."""
    gen = TestGenerator(llm=MagicMock())
    session = MagicMock()
    session.rounds = [MagicMock()]  # has prior rounds -> feedback path
    with patch.object(gen, "_generate_once", return_value=_suite("x")) as once:
        gen.generate(_fi(), oracle="correctness", samples=5, existing_session=session)
        assert once.call_count == 1


def test_verification_manager_passes_oracle_and_samples():
    """Regression: the VM previously did not pass oracle to generate(), so
    round-0 generation always used the default crash oracle regardless of
    --oracle. The VM must forward both oracle and samples."""
    from qallm.verification.verification_manager import VerificationManager
    llm = MagicMock(); llm.name.return_value = "m"
    vm = VerificationManager(llm=llm, tracker=MagicMock(),
                             oracle="correctness", samples=4)
    assert vm.oracle == "correctness"
    assert vm.samples == 4
