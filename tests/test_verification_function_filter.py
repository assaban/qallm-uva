"""Tests for the original-functions-only filter in VerificationManager.verify.

Background
----------

A repaired code unit can have a different function set from the original:

* The LLM might add helper functions during repair (e.g., extracting common
  logic into ``_helper`` or ``_validate_input``).
* Even with private-function filtering in the extractor, the LLM might
  add public functions to refactor existing code.

Verifying those new functions is tautological: we'd be testing the LLM's
own additions with the LLM's own tests, which doesn't measure anything
useful and wastes budget. The verification stage therefore filters to
functions that existed in the *original* code unit.

These tests exercise that filter in isolation, with a mocked executor and
LLM, so they run fast and don't depend on real model calls.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch


from qallm.repair.repair_model import RepairedCodeUnit, RepairResult
from qallm.analysis.analysis_model import AnalysedCodeUnit
from qallm.common.model import CodeUnit
from qallm.verification.verification_manager import VerificationManager
from qallm.verification.test_persistence import (
    GenerationPolicy,
    TestStability,
    TestStabilityConfig,
)


def _build_repaired_unit(
    original_source: str,
    repaired_source: str,
    path: Path,
) -> RepairedCodeUnit:
    """Construct a RepairedCodeUnit with separately-controlled original
    and repaired source code.

    This matches the real construction path: AnalysedCodeUnit holds the
    original; RepairResult holds the repaired bytes; RepairedCodeUnit
    builds the post-repair CodeUnit and remembers the original.
    """
    original_unit = CodeUnit(
        source_code=original_source,
        original_path=path,
        cell_index=0,
    )
    analysed = AnalysedCodeUnit(code_unit=original_unit)
    repair_result = RepairResult(
        file_path=str(path),
        repaired_source=repaired_source,
        explanation="for tests",
        compiles=True,
    )
    return RepairedCodeUnit(
        analysis_result=analysed,
        repaired_result=repair_result,
    )


def _make_verification_manager() -> VerificationManager:
    """A minimal VerificationManager with no real LLM or executor."""
    llm = MagicMock()
    llm.name = lambda: "stub"
    return VerificationManager(
        llm=llm,
        tracker=MagicMock(),
        oracle="crash",
        total_rounds=1,
        stability_config=TestStabilityConfig(
            stability=TestStability.FROZEN,
            policy=GenerationPolicy.REPLAY_ONLY,
        ),
    )


class TestOriginalOnlyFiltering:
    """Functions that didn't exist in the original code are not verified."""

    def test_function_added_during_repair_is_skipped(self, tmp_path, caplog):
        original_source = (
            "def add(a, b):\n"
            "    return a + b\n"
        )
        # Repair "improves" the code by adding a helper. Tests should
        # cover only `add` (in both sets); not `validate` (new in repaired).
        repaired_source = (
            "def validate(x):\n"
            "    if x is None:\n"
            "        raise ValueError\n"
            "    return x\n"
            "\n"
            "def add(a, b):\n"
            "    return validate(a) + validate(b)\n"
        )

        unit = _build_repaired_unit(
            original_source, repaired_source, tmp_path / "demo.py",
        )
        vm = _make_verification_manager()

        # Stub the per-function execution so verify() returns quickly.
        with patch.object(vm.generator, "generate") as fake_gen, \
             patch("qallm.verification.verification_manager.run_tests") as fake_run:
            fake_gen.return_value = MagicMock(
                test_code="def test_dummy(): pass", is_valid=True,
                generation_error=None, oracle="crash", model="stub",
                provider="stub",
            )
            fake_run.return_value = MagicMock(
                stdout="", stderr="", execution_error=None,
                tests_passed=1, tests_failed=0, tests_errored=0,
                coverage_percent=100.0, bugs_found=0,
            )

            with caplog.at_level(logging.INFO):
                # tested = vm.verify(unit, round_number=1)
                vm.verify(unit, round_number=1)

            # Generator was called for `add` but NOT for `validate`.
            called_func_names = [
                call.kwargs.get("func", call.args[0] if call.args else None).name
                for call in fake_gen.call_args_list
            ]
            assert called_func_names == ["add"]

            # And the log records the skip clearly so the user can audit.
            assert any(
                "Skipping" in r.message and "validate" in r.message
                for r in caplog.records
            )

    def test_function_removed_during_repair_is_silently_dropped(self, tmp_path):
        # If repair *removes* a function (e.g., consolidates it into another),
        # we have nothing to verify for that name. No error, just nothing.
        original_source = (
            "def add(a, b):\n"
            "    return a + b\n"
            "\n"
            "def subtract(a, b):\n"
            "    return a - b\n"
        )
        repaired_source = (
            "def add(a, b):\n"
            "    return a + b\n"
        )

        unit = _build_repaired_unit(
            original_source, repaired_source, tmp_path / "demo.py",
        )
        vm = _make_verification_manager()

        with patch.object(vm.generator, "generate") as fake_gen, \
             patch("qallm.verification.verification_manager.run_tests") as fake_run:
            fake_gen.return_value = MagicMock(
                test_code="def test_dummy(): pass", is_valid=True,
                generation_error=None, oracle="crash", model="stub",
                provider="stub",
            )
            fake_run.return_value = MagicMock(
                stdout="", stderr="", execution_error=None,
                tests_passed=1, tests_failed=0, tests_errored=0,
                coverage_percent=100.0, bugs_found=0,
            )

            vm.verify(unit, round_number=1)

            called_func_names = [
                call.kwargs.get("func", call.args[0] if call.args else None).name
                for call in fake_gen.call_args_list
            ]
            # Only `add` is in the intersection of (original, repaired).
            assert called_func_names == ["add"]

    def test_identical_source_verifies_all_originals(self, tmp_path):
        # When repair didn't change the function set (e.g., body edits only),
        # all originals are verified.
        source = (
            "def add(a, b):\n"
            "    return a + b\n"
            "\n"
            "def subtract(a, b):\n"
            "    return a - b\n"
        )

        unit = _build_repaired_unit(source, source, tmp_path / "demo.py")
        vm = _make_verification_manager()

        with patch.object(vm.generator, "generate") as fake_gen, \
             patch("qallm.verification.verification_manager.run_tests") as fake_run:
            fake_gen.return_value = MagicMock(
                test_code="def test_dummy(): pass", is_valid=True,
                generation_error=None, oracle="crash", model="stub",
                provider="stub",
            )
            fake_run.return_value = MagicMock(
                stdout="", stderr="", execution_error=None,
                tests_passed=1, tests_failed=0, tests_errored=0,
                coverage_percent=100.0, bugs_found=0,
            )

            vm.verify(unit, round_number=1)

            called_func_names = sorted([
                call.kwargs.get("func", call.args[0] if call.args else None).name
                for call in fake_gen.call_args_list
            ])
            assert called_func_names == ["add", "subtract"]

    def test_private_functions_still_filtered_by_extractor(self, tmp_path):
        # Sanity: the extractor's existing _private filter still applies.
        # Even if repair adds public functions, _private ones are skipped
        # at the extraction layer, regardless of the original/repaired
        # intersection logic.
        original_source = (
            "def add(a, b):\n"
            "    return a + b\n"
            "\n"
            "def _helper(x):\n"
            "    return x * 2\n"
        )
        repaired_source = (
            "def add(a, b):\n"
            "    return a + b\n"
            "\n"
            "def _helper(x):\n"
            "    return x * 2\n"
        )

        unit = _build_repaired_unit(
            original_source, repaired_source, tmp_path / "demo.py",
        )
        vm = _make_verification_manager()

        with patch.object(vm.generator, "generate") as fake_gen, \
             patch("qallm.verification.verification_manager.run_tests") as fake_run:
            fake_gen.return_value = MagicMock(
                test_code="def test_dummy(): pass", is_valid=True,
                generation_error=None, oracle="crash", model="stub",
                provider="stub",
            )
            fake_run.return_value = MagicMock(
                stdout="", stderr="", execution_error=None,
                tests_passed=1, tests_failed=0, tests_errored=0,
                coverage_percent=100.0, bugs_found=0,
            )

            vm.verify(unit, round_number=1)

            called_func_names = [
                call.kwargs.get("func", call.args[0] if call.args else None).name
                for call in fake_gen.call_args_list
            ]
            assert "_helper" not in called_func_names
            assert called_func_names == ["add"]


class TestSessionSourceRefresh:
    """The reused per-function session reflects each round's actual source.

    Regression: a function whose body was repaired but whose session is
    reused across rounds used to keep its round-0 source_code forever, so the
    report's "Function under test" showed the original (pre-repair) code every
    round even though the code on disk was correctly repaired.
    """

    def test_reused_session_source_updates_after_repair(self, tmp_path):
        path = tmp_path / "demo.py"
        original_source = "def f(x):\n    return eval(x)\n"
        repaired_source = "def f(x):\n    return ast.literal_eval(x)\n"

        vm = _make_verification_manager()

        # Round 1 runs against the original source.
        unit_r1 = _build_repaired_unit(original_source, original_source, path)
        # Round 2 runs against the repaired source for the same function.
        unit_r2 = _build_repaired_unit(original_source, repaired_source, path)

        with patch.object(vm.generator, "generate") as fake_gen, \
             patch("qallm.verification.verification_manager.run_tests") as fake_run:
            fake_gen.return_value = MagicMock(
                test_code="def test_dummy(): pass", is_valid=True,
                generation_error=None, oracle="crash", model="stub",
                provider="stub",
            )
            fake_run.return_value = MagicMock(
                stdout="", stderr="", execution_error=None,
                tests_passed=1, tests_failed=0, tests_errored=0,
                coverage_percent=100.0, bugs_found=0,
            )

            vm.verify(unit_r1, round_number=1)
            key = vm.store.make_key(path, 0, "f")
            session_after_r1 = vm.store.get_or_create_record(key, "f").session
            assert "eval(x)" in session_after_r1.source_code

            vm.verify(unit_r2, round_number=2)
            session_after_r2 = vm.store.get_or_create_record(key, "f").session
            # Same persisted session, but its source now reflects round 2.
            assert session_after_r2 is session_after_r1
            assert "ast.literal_eval(x)" in session_after_r2.source_code
            assert "return eval(x)" not in session_after_r2.source_code


class TestBaselineGate:
    """The baseline gate (Bug 2): a generated test that fails on the ORIGINAL
    code is stripped, since the original is the reference, the test is wrong,
    not the code. Prevents false bugs on correct functions and the 0% HumanEval
    detection signature."""

    def test_test_failing_on_original_is_stripped(self, tmp_path, caplog):
        from qallm.verification.models import TestDetail

        original_source = "def add(a, b):\n    return a + b\n"
        unit = _build_repaired_unit(
            original_source, original_source, tmp_path / "demo.py",
        )
        vm = _make_verification_manager()
        # GROW so freshly generated tests are run (gate is on generation path).
        vm.stability_config = TestStabilityConfig(
            stability=TestStability.FROZEN, policy=GenerationPolicy.GROW,
        )

        gen = MagicMock(
            test_code=(
                "def test_ok():\n    assert add(1, 2) == 3\n\n"
                "def test_wrong():\n    assert add(1, 1) == 3\n"
            ),
            is_valid=True, generation_error=None, oracle="crash",
            model="stub", provider="stub", discarded_tests=[],
            input_tokens=0, output_tokens=0,
        )

        def fake_run(source, test_code, *a, **k):
            # The gate runs against original_source: test_wrong fails there.
            if "test_wrong" in test_code and source == original_source:
                return MagicMock(
                    test_details=[
                        TestDetail(name="test_ok", status="passed"),
                        TestDetail(name="test_wrong", status="failed"),
                    ],
                    passed=1, failed=1, errors=0, coverage_percent=100.0,
                    execution_error=None,
                )
            # Subsequent runs (variant) see only the surviving test.
            return MagicMock(
                test_details=[TestDetail(name="test_ok", status="passed")],
                passed=1, failed=0, errors=0, coverage_percent=100.0,
                execution_error=None,
            )

        with patch.object(vm.generator, "generate", return_value=gen), \
             patch("qallm.verification.verification_manager.run_tests", side_effect=fake_run):
            with caplog.at_level(logging.INFO):
                vm.verify(unit, round_number=1)

        # test_wrong (fails on the original) was stripped; test_ok survives.
        assert "test_wrong" not in gen.test_code
        assert "def test_ok" in gen.test_code
        assert any("baseline-gate" in r.getMessage() for r in caplog.records)


    def test_gate_does_not_run_at_round_0(self, tmp_path, caplog):
        """Round 0 is the gap-detection pass: a test that fails the original
        is the signal, not noise, and must NOT be stripped. Gating round 0
        would erase exactly the bugs the experiment measures."""
        from qallm.verification.models import TestDetail

        # Original code is buggy here (the round-0 case for reliability_gap).
        original_source = "def add(a, b):\n    return a - b  # BUG\n"
        unit = _build_repaired_unit(
            original_source, original_source, tmp_path / "demo.py",
        )
        vm = _make_verification_manager()

        gen = MagicMock(
            test_code="def test_add():\n    assert add(1, 2) == 3\n",
            is_valid=True, generation_error=None, oracle="crash",
            model="stub", provider="stub", discarded_tests=[],
            input_tokens=0, output_tokens=0,
        )

        run_calls = []

        def fake_run(source, test_code, *a, **k):
            run_calls.append(test_code)
            # The (buggy) original fails this correct test, that is the gap.
            return MagicMock(
                test_details=[TestDetail(name="test_add", status="failed")],
                passed=0, failed=1, errors=0, coverage_percent=100.0,
                execution_error=None,
            )

        with patch.object(vm.generator, "generate", return_value=gen), \
             patch("qallm.verification.verification_manager.run_tests", side_effect=fake_run):
            with caplog.at_level(logging.INFO):
                vm.verify(unit, round_number=0)

        # The bug-catching test survives (not stripped) and no gate ran.
        assert "def test_add" in gen.test_code
        assert not any("baseline-gate" in r.getMessage() for r in caplog.records)
