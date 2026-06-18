"""Tests for `qallm.verification.test_persistence` and the integration into
`VerificationManager`.

These tests cover the configuration matrix (three valid combinations, one
rejected), the store's persistence semantics, and the manager's branching
behaviour for each mode.

The integration-style tests mock the LLM and the executor to avoid making real
API calls or running real pytest subprocesses; the focus is on whether the
verification manager makes the right decisions, not on test correctness.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from qallm.verification.models import (
    ExecutionResult,
    GeneratedTest,
)
from qallm.verification.test_persistence import (
    GenerationPolicy,
    TestStability,
    TestStabilityConfig,
    TestSuiteStore,
)


# ---------- TestStabilityConfig ----------


class TestConfigValidation:
    def test_default_is_frozen_grow(self) -> None:
        cfg = TestStabilityConfig()
        assert cfg.stability is TestStability.FROZEN
        assert cfg.policy is GenerationPolicy.GROW

    def test_frozen_replay_is_valid(self) -> None:
        cfg = TestStabilityConfig(
            stability=TestStability.FROZEN,
            policy=GenerationPolicy.REPLAY_ONLY,
        )
        assert cfg.stability is TestStability.FROZEN
        assert cfg.policy is GenerationPolicy.REPLAY_ONLY

    def test_per_round_grow_is_valid(self) -> None:
        cfg = TestStabilityConfig(
            stability=TestStability.PER_ROUND,
            policy=GenerationPolicy.GROW,
        )
        assert cfg.stability is TestStability.PER_ROUND

    def test_per_round_replay_only_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="degenerate"):
            TestStabilityConfig(
                stability=TestStability.PER_ROUND,
                policy=GenerationPolicy.REPLAY_ONLY,
            )

    def test_to_dict_round_trips_strings(self) -> None:
        cfg = TestStabilityConfig.from_strings(
            stability="frozen", policy="grow"
        )
        assert cfg.to_dict() == {
            "test_stability": "frozen",
            "generation_policy": "grow",
        }


# ---------- TestSuiteStore ----------


def _make_generated_test(
    function_name: str = "f",
    test_code: str = "def test_x(): assert True",
    is_valid: bool = True,
) -> GeneratedTest:
    return GeneratedTest(
        function_name=function_name,
        oracle="crash",
        test_code=test_code,
        is_valid=is_valid,
        generation_error=None,
        model="gpt-4o-mini",
        provider="openai",
        input_tokens=10,
        output_tokens=20,
    )


@pytest.fixture
def example_key(tmp_path: Path) -> tuple:
    src = tmp_path / "mod.py"
    src.write_text("def f(): pass\n")
    return TestSuiteStore.make_key(src, -1, "f")


class TestSuiteStoreBasics:
    def test_make_key_is_stable(self, tmp_path: Path) -> None:
        src = tmp_path / "mod.py"
        src.write_text("def f(): pass\n")
        k1 = TestSuiteStore.make_key(src, -1, "f")
        k2 = TestSuiteStore.make_key(src, -1, "f")
        assert k1 == k2
        assert k1[2] == "f"

    def test_record_and_replay(self, example_key) -> None:
        store = TestSuiteStore(TestStabilityConfig())
        gt = _make_generated_test()
        store.record_generated(example_key, "f", gt, round_number=1)

        replayed = store.replay_tests(example_key)
        assert len(replayed) == 1
        assert replayed[0].test_code == gt.test_code
        assert replayed[0].generated_in_round == 1

    def test_invalid_tests_not_replayed(self, example_key) -> None:
        store = TestSuiteStore(TestStabilityConfig())
        valid = _make_generated_test(test_code="def test_a(): pass", is_valid=True)
        invalid = _make_generated_test(test_code="garbage", is_valid=False)
        store.record_generated(example_key, "f", valid, round_number=1)
        store.record_generated(example_key, "f", invalid, round_number=2)

        replayed = store.replay_tests(example_key)
        assert len(replayed) == 1
        assert replayed[0].test_code == "def test_a(): pass"


class TestShouldGenerate:
    def test_frozen_replay_only_generates_once(self, example_key) -> None:
        store = TestSuiteStore(
            TestStabilityConfig(
                stability=TestStability.FROZEN,
                policy=GenerationPolicy.REPLAY_ONLY,
            )
        )
        # Round 0: no record yet, must generate
        assert store.should_generate(example_key) is True

        # Record a valid test
        gt = _make_generated_test()
        store.record_generated(example_key, "f", gt, round_number=1)

        # Round 1: stored tests exist, must NOT regenerate
        assert store.should_generate(example_key) is False

    def test_frozen_replay_only_regenerates_if_no_valid_test(self, example_key) -> None:
        store = TestSuiteStore(
            TestStabilityConfig(
                stability=TestStability.FROZEN,
                policy=GenerationPolicy.REPLAY_ONLY,
            )
        )
        # Record only an invalid test
        gt = _make_generated_test(is_valid=False)
        store.record_generated(example_key, "f", gt, round_number=1)

        # Round 2: still no valid tests, should try again
        assert store.should_generate(example_key) is True

    def test_frozen_grow_always_generates(self, example_key) -> None:
        store = TestSuiteStore(
            TestStabilityConfig(
                stability=TestStability.FROZEN,
                policy=GenerationPolicy.GROW,
            )
        )
        for round_n in range(1, 5):
            assert store.should_generate(example_key) is True
            store.record_generated(
                example_key, "f", _make_generated_test(), round_number=round_n
            )

    def test_per_round_grow_always_generates(self, example_key) -> None:
        store = TestSuiteStore(
            TestStabilityConfig(
                stability=TestStability.PER_ROUND,
                policy=GenerationPolicy.GROW,
            )
        )
        assert store.should_generate(example_key) is True


class TestCarriesTests:
    def test_frozen_carries(self) -> None:
        store = TestSuiteStore(TestStabilityConfig())  # default = frozen
        assert store.carries_tests() is True

    def test_per_round_does_not_carry(self) -> None:
        store = TestSuiteStore(
            TestStabilityConfig(
                stability=TestStability.PER_ROUND,
                policy=GenerationPolicy.GROW,
            )
        )
        assert store.carries_tests() is False


class TestClearForRound:
    def test_clear_under_per_round_drops_tests(self, example_key) -> None:
        store = TestSuiteStore(
            TestStabilityConfig(
                stability=TestStability.PER_ROUND,
                policy=GenerationPolicy.GROW,
            )
        )
        store.record_generated(
            example_key, "f", _make_generated_test(), round_number=1
        )
        assert len(store.replay_tests(example_key)) == 1

        store.clear_for_round()
        assert store.replay_tests(example_key) == []

    def test_clear_under_frozen_is_noop(self, example_key) -> None:
        store = TestSuiteStore(TestStabilityConfig())  # frozen default
        store.record_generated(
            example_key, "f", _make_generated_test(), round_number=1
        )
        store.clear_for_round()
        assert len(store.replay_tests(example_key)) == 1


class TestSummary:
    def test_summary_counts_unique_code_units(
        self, tmp_path: Path
    ) -> None:
        store = TestSuiteStore(TestStabilityConfig())

        # Two distinct code units, three tests total across them
        src_a = tmp_path / "a.py"
        src_a.write_text("def f(): pass\n")
        src_b = tmp_path / "b.py"
        src_b.write_text("def g(): pass\n")

        key_a = TestSuiteStore.make_key(src_a, -1, "f")
        key_b = TestSuiteStore.make_key(src_b, -1, "g")

        store.record_generated(
            key_a, "f", _make_generated_test(test_code="def test_a(): assert f() is None"), 1
        )
        store.record_generated(
            key_a, "f", _make_generated_test(test_code="def test_b(): assert f() == None"), 2
        )
        store.record_generated(key_b, "g", _make_generated_test(), 1)

        summary = store.summary()
        assert summary["code_units_with_tests"] == 2
        assert summary["total_tests_stored"] == 3
        assert summary["test_stability"] == "frozen"
        assert summary["generation_policy"] == "grow"


class TestStorePersistence:
    def test_save_writes_json(self, example_key, tmp_path: Path) -> None:
        store = TestSuiteStore(TestStabilityConfig())
        store.record_generated(
            example_key, "f", _make_generated_test(), round_number=1
        )

        out_path = store.save(tmp_path / "store_out")
        assert out_path.exists()
        text = out_path.read_text(encoding="utf-8")
        assert "frozen" in text  # config serialised
        assert "grow" in text


# ---------- VerificationManager integration ----------


def _make_repaired_unit(tmp_path: Path, source_code: str = None):
    """Construct a RepairedCodeUnit pointing at a temp source file."""
    from qallm.common.model import CodeUnit
    from qallm.repair.repair_model import RepairedCodeUnit, RepairResult
    from qallm.analysis.analysis_model import AnalysedCodeUnit

    if source_code is None:
        source_code = "def add(a, b):\n    return a + b\n"
    src = tmp_path / "calc.py"
    src.write_text(source_code)

    original = CodeUnit(
        source_code=source_code,
        original_path=src,
        cell_index=-1,
    )
    analysed = AnalysedCodeUnit(code_unit=original, findings=[], raw_tool_results=[])
    repaired_result = RepairResult(
        file_path=str(src),
        repaired_source=source_code,
        explanation="no changes",
        compiles=True,
    )
    return RepairedCodeUnit(analysis_result=analysed, repaired_result=repaired_result)


@pytest.fixture
def stub_llm():
    """A fake LLM whose `name()` returns a fixed string. The TestGenerator inside
    VerificationManager will be patched per-test where needed."""
    llm = MagicMock()
    llm.name.return_value = "stub-model"
    return llm


@pytest.fixture
def stub_tracker():
    tracker = MagicMock()
    tracker.to_dict.return_value = {"total_cost_usd": 0.0}
    return tracker


def _ok_execution() -> ExecutionResult:
    """A successful execution result with 100% coverage and zero failed tests
    (so `bugs_found` property returns 0)."""
    return ExecutionResult(
        passed=1,
        failed=0,
        errors=0,
        total=1,
        coverage_percent=100.0,
    )


class TestVerificationManagerModes:
    def test_frozen_replay_only_does_not_call_generator_twice(
        self, tmp_path: Path, stub_llm, stub_tracker
    ) -> None:
        from qallm.verification.verification_manager import VerificationManager

        cfg = TestStabilityConfig(
            stability=TestStability.FROZEN,
            policy=GenerationPolicy.REPLAY_ONLY,
        )
        manager = VerificationManager(
            llm=stub_llm,
            tracker=stub_tracker,
            stability_config=cfg,
        )
        # Replace the generator with a mock that returns a fixed valid test
        gen_mock = MagicMock()
        gen_mock.llm.name.return_value = "stub-model"
        gen_mock.generate.return_value = _make_generated_test(
            test_code="def test_add(): assert True"
        )
        manager.generator = gen_mock

        unit = _make_repaired_unit(tmp_path)

        with patch(
            "qallm.verification.verification_manager.run_tests",
            return_value=_ok_execution(),
        ):
            manager.verify(unit, round_number=1)
            manager.verify(unit, round_number=2)
            manager.verify(unit, round_number=3)

        # Generator was called exactly once (round 1), then we replayed.
        assert gen_mock.generate.call_count == 1

    def test_frozen_grow_calls_generator_every_round(
        self, tmp_path: Path, stub_llm, stub_tracker
    ) -> None:
        from qallm.verification.verification_manager import VerificationManager

        cfg = TestStabilityConfig(
            stability=TestStability.FROZEN,
            policy=GenerationPolicy.GROW,
        )
        manager = VerificationManager(
            llm=stub_llm,
            tracker=stub_tracker,
            stability_config=cfg,
        )
        gen_mock = MagicMock()
        gen_mock.llm.name.return_value = "stub-model"
        gen_mock.generate.return_value = _make_generated_test(
            test_code="def test_grow(): assert True"
        )
        manager.generator = gen_mock

        unit = _make_repaired_unit(tmp_path)

        with patch(
            "qallm.verification.verification_manager.run_tests",
            return_value=_ok_execution(),
        ):
            manager.verify(unit, round_number=1)
            manager.verify(unit, round_number=2)
            manager.verify(unit, round_number=3)

        # Generator called once per round
        assert gen_mock.generate.call_count == 3

    def test_per_round_grow_calls_generator_every_round(
        self, tmp_path: Path, stub_llm, stub_tracker
    ) -> None:
        from qallm.verification.verification_manager import VerificationManager

        cfg = TestStabilityConfig(
            stability=TestStability.PER_ROUND,
            policy=GenerationPolicy.GROW,
        )
        manager = VerificationManager(
            llm=stub_llm,
            tracker=stub_tracker,
            stability_config=cfg,
        )
        gen_mock = MagicMock()
        gen_mock.llm.name.return_value = "stub-model"
        gen_mock.generate.return_value = _make_generated_test(
            test_code="def test_per_round(): assert True"
        )
        manager.generator = gen_mock

        unit = _make_repaired_unit(tmp_path)

        with patch(
            "qallm.verification.verification_manager.run_tests",
            return_value=_ok_execution(),
        ):
            manager.verify(unit, round_number=1)
            manager.verify(unit, round_number=2)

        assert gen_mock.generate.call_count == 2

    def test_summary_contains_stability_info(
        self, tmp_path: Path, stub_llm, stub_tracker
    ) -> None:
        from qallm.verification.verification_manager import VerificationManager

        cfg = TestStabilityConfig(
            stability=TestStability.FROZEN,
            policy=GenerationPolicy.REPLAY_ONLY,
        )
        manager = VerificationManager(
            llm=stub_llm,
            tracker=stub_tracker,
            stability_config=cfg,
        )
        summary = manager.get_stability_summary()
        assert summary["test_stability"] == "frozen"
        assert summary["generation_policy"] == "replay_only"
