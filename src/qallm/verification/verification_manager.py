"""Verification Manager: RL-guided test generation with incremental persistence.

Within a QALLM round, test generation behaviour depends on the
`TestStabilityConfig` (see `qallm.verification.test_persistence`):

* FROZEN + REPLAY_ONLY: generate once per code unit (round 0), then replay
  the same tests against every subsequent variant.
* FROZEN + GROW: generate per round, accumulating tests; later rounds run
  against the full union of previously-generated tests.
* PER_ROUND + GROW: generate fresh tests each round; no carry-over.

After each function completes, artifacts are saved immediately to disk.
"""

import dataclasses
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional

from qallm.verification.models import ExecutionResult
from qallm.repair.repair_model import RepairedCodeUnit
from .extractor import extract_functions_from_source
from .generator import TestGenerator
from .executor import run_tests
from .models import TestGenerationSession, RoundResult, TestedCodeUnit
from .reward import compute_reward
from .test_persistence import (
    GenerationPolicy,
    StoredTest,
    TestStability,
    TestStabilityConfig,
    TestSuiteStore,
)

logger = logging.getLogger(__name__)


def _concatenate_test_codes(stored: list[StoredTest]) -> str:
    """Combine multiple stored test files into a single pytest module.

    Each test's source is included with a small header indicating its origin
    round. pytest is happy with multiple `def test_*` functions in one file
    and we get a single coverage report.
    """
    parts: list[str] = []
    for i, t in enumerate(stored):
        parts.append(f"# --- stored test {i + 1} (generated in round {t.generated_in_round}) ---")
        parts.append(t.test_code.strip())
        parts.append("")  # blank line between blocks
    return "\n".join(parts)


class VerificationManager:
    def __init__(
        self,
        llm,
        tracker,
        oracle: str = "crash",
        total_rounds: int = 5,
        stability_config: Optional[TestStabilityConfig] = None,
    ):
        self.generator = TestGenerator(llm, tracker=tracker)
        self.oracle = oracle
        self.total_rounds = total_rounds
        self.stability_config = stability_config or TestStabilityConfig()
        self.store = TestSuiteStore(self.stability_config)
        logger.info(
            "VerificationManager initialised with stability=%s, policy=%s",
            self.stability_config.stability.value,
            self.stability_config.policy.value,
        )

    def get_session_data(self) -> list[dict]:
        """Formats sessions for the summary report and CLI output."""
        session_data = []
        for session in self.store.all_sessions():
            data = dataclasses.asdict(session)
            data["function"] = session.function_name
            data["final_coverage"] = session.final_coverage
            data["final_bugs"] = session.final_bugs
            data["learning_curve"] = session.learning_curve
            session_data.append(data)
        return session_data

    def get_stability_summary(self) -> dict:
        """Surface the test-stability state for inclusion in summary.json."""
        return self.store.summary()

    def verify(
        self,
        repaired_unit: RepairedCodeUnit,
        persist_dir: Optional[Path] = None,
        on_function_complete: Optional[Callable] = None,
        on_function_start: Optional[Callable] = None,
        round_number: int = 1,
    ) -> TestedCodeUnit:
        """Verify a repaired code unit. Behaviour depends on stability config.

        For each function in the unit:
          1. Resolve a stable key (path, cell, function).
          2. Ask the store whether to generate fresh tests or replay stored ones.
          3. If generating: call the LLM, optionally append to the store.
          4. If replaying: concatenate stored test codes; run them; no LLM call.
          5. Record the round result on the session; persist to disk if asked.

        Args:
            repaired_unit: the variant under verification.
            persist_dir: where to save per-function artefacts.
            on_function_complete: callback after each function finishes.
                Signature: ``(name, session, idx, total)``.
            on_function_start: callback before each function begins (BEFORE
                the LLM call). Critical for progress visibility on slow local
                models: without this, the orchestrator's snapshot would stay
                on the previous function's name for the full duration of the
                next function's LLM call. Signature: ``(name, idx, total)``.
            round_number: 1-indexed QALLM round number. Used to label stored
                tests with their origin round.
        """
        unit = repaired_unit.repaired_code_unit
        source, path = unit.source_code, unit.original_path

        # Extract functions from the *repaired* source: this is what we
        # actually run tests against.
        functions = extract_functions_from_source(source, str(path))

        # Filter to functions that existed in the original code. A round-N
        # variant may introduce new helpers added by the LLM during repair;
        # verifying those is tautological (LLM tests its own additions)
        # and wastes budget. We test only what the user originally wrote.
        original_source = repaired_unit.original_code_unit.source_code
        original_function_names = {
            f.name for f in extract_functions_from_source(
                original_source, str(path),
            )
        }
        skipped_new = [f.name for f in functions
                       if f.name not in original_function_names]
        functions = [f for f in functions
                     if f.name in original_function_names]
        if skipped_new:
            logger.info(
                "Skipping %d function(s) added during repair (not in original): %s",
                len(skipped_new), skipped_new,
            )

        unit_sessions: list[TestGenerationSession] = []

        for func_idx, func in enumerate(functions):
            # Fire the start callback BEFORE any slow work. This is what
            # lets the UI show "verifying function 3 of 8: predict" while
            # the LLM call is actually in flight, rather than only after
            # the call returns.
            if on_function_start:
                try:
                    on_function_start(func.name, func_idx + 1, len(functions))
                except Exception as e:
                    # A buggy callback must not abort verification. Log and
                    # continue.
                    logger.warning(
                        "on_function_start callback raised: %s", e,
                    )

            key = TestSuiteStore.make_key(path, unit.cell_index, func.name)
            record = self.store.get_or_create_record(key, func.name)

            # Reuse or create the session.
            if record.session is None:
                session = TestGenerationSession(
                    function_name=func.name,
                    source_code=source,
                    oracle=self.oracle,
                    model=self.generator.llm.name(),
                    total_rounds=self.total_rounds,
                )
                self.store.attach_session(key, session)
            else:
                session = record.session

            module_name = f"source_{path.stem}_c{unit.cell_index}"

            logger.info(
                "Verifying %s [%d/%d] in round %d (stability=%s, policy=%s)",
                func.name,
                func_idx + 1,
                len(functions),
                round_number,
                self.stability_config.stability.value,
                self.stability_config.policy.value,
            )

            # ----- decide: generate or replay -----
            generate = self.store.should_generate(key)
            test_code_to_run: str = ""
            generated = None

            if generate:
                generated = self.generator.generate(
                    func, module_name=module_name, existing_session=session
                )
                # Record only valid tests in the store under FROZEN modes;
                # under PER_ROUND we still record so artefacts are tracked.
                if self.store.carries_tests() or self.stability_config.policy is GenerationPolicy.GROW:
                    self.store.record_generated(
                        key, func.name, generated, round_number
                    )
                test_code_to_run = generated.test_code if generated.is_valid else ""
            else:
                # Replay: build a combined test module from stored tests.
                stored = self.store.replay_tests(key)
                if not stored:
                    logger.warning(
                        "Replay requested for %s but no stored tests found; skipping",
                        func.name,
                    )
                    test_code_to_run = ""
                else:
                    test_code_to_run = _concatenate_test_codes(stored)
                    logger.info(
                        "Replaying %d stored test(s) for %s against round-%d variant",
                        len(stored),
                        func.name,
                        round_number,
                    )

            # Under FROZEN + GROW with prior tests in store, we also replay
            # prior tests against the new variant in addition to running the
            # freshly generated ones. Concatenate everything we have.
            if (
                self.stability_config.stability is TestStability.FROZEN
                and self.stability_config.policy is GenerationPolicy.GROW
                and generated is not None
                and generated.is_valid
            ):
                all_stored = self.store.replay_tests(key)
                if len(all_stored) > 1:
                    test_code_to_run = _concatenate_test_codes(all_stored)
                    logger.info(
                        "FROZEN+GROW: running %d accumulated test(s) for %s",
                        len(all_stored),
                        func.name,
                    )

            # ----- execute -----
            if test_code_to_run:
                execution = run_tests(
                    source, test_code_to_run, f"{module_name}.py", path
                )
            else:
                error_msg = (
                    f"Skipped: {generated.generation_error or 'invalid test code'}"
                    if generated
                    else "Skipped: no tests available to run"
                )
                execution = ExecutionResult(execution_error=error_msg)

            reward = compute_reward(execution, session.final_coverage)

            # Use a placeholder GeneratedTest for replay rounds, since there's
            # no fresh generation. We mark it as a replay for transparency.
            from qallm.verification.models import GeneratedTest as _GT
            generated_for_record = generated or _GT(
                function_name=func.name,
                oracle=self.oracle,
                test_code=test_code_to_run,
                is_valid=bool(test_code_to_run),
                generation_error=None,
                model=f"replay (round {round_number})",
                provider="store",
                input_tokens=0,
                output_tokens=0,
            )

            session.rounds.append(
                RoundResult(
                    round_number=len(session.rounds) + 1,
                    generated_test=generated_for_record,
                    execution=execution,
                    reward=reward,
                    cumulative_coverage=max(
                        session.final_coverage or 0.0,
                        execution.coverage_percent or 0.0,
                    )
                    if execution
                    else 0.0,
                    cumulative_bugs=session.final_bugs
                    + (execution.bugs_found if execution else 0),
                )
            )

            logger.info(
                "  %s: reward=%.2f, coverage=%.1f%%, bugs=%d, valid=%s",
                func.name,
                reward.total,
                execution.coverage_percent or 0.0,
                execution.bugs_found if execution else 0,
                generated_for_record.is_valid,
            )

            # Incremental persistence: save immediately after each function
            if persist_dir:
                self._save_function_artifacts(session, func, persist_dir, path.stem)

            # Callback for real-time updates
            if on_function_complete:
                on_function_complete(func.name, session, func_idx + 1, len(functions))

            unit_sessions.append(session)

        return TestedCodeUnit(repaired_unit=repaired_unit, sessions=unit_sessions)

    def _save_function_artifacts(
        self, session: TestGenerationSession, func, persist_dir: Path, file_stem: str
    ) -> None:
        """Save test code + session JSON immediately after a function completes."""
        tests_dir = persist_dir / "generated_tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        # Save the generated test file
        if session.rounds:
            last_round = session.rounds[-1]
            if last_round.generated_test.is_valid:
                test_filename = f"test_{file_stem}_{session.function_name}_r{len(session.rounds)}.py"
                (tests_dir / test_filename).write_text(
                    last_round.generated_test.test_code, encoding="utf-8"
                )

        # Save the session JSON (overwritten each round, always up to date)
        session_path = tests_dir / f"session_{session.function_name}.json"
        _save_session(session, session_path)


def _save_session(session: TestGenerationSession, output_path: Path) -> None:
    """Persist a verification session as JSON for reproducibility.

    Includes computed properties (final_coverage, final_bugs, learning_curve)
    which are @property methods not captured by dataclasses.asdict().
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(session)
    data["final_coverage"] = session.final_coverage
    data["final_bugs"] = session.final_bugs
    data["learning_curve"] = session.learning_curve
    data["reward_per_round"] = session.reward_per_round
    output_path.write_text(
        json.dumps(data, indent=2, default=str),
        encoding="utf-8",
    )


# Keep the old import path working
save_session = _save_session
