"""Verification Manager: RL-guided test generation with incremental persistence.

Within a QALLM round (Option A), test generation runs ONCE per function.
The multi-round learning happens at the orchestrator level across QALLM rounds
(repair → analyse → verify → report), not within test generation.

After each function completes, artifacts are saved immediately to disk.
"""

import dataclasses
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Callable, Optional

from qallm.verification.models import ExecutionResult
from qallm.repair.repair_model import RepairedCodeUnit
from .extractor import extract_functions_from_source
from .generator import TestGenerator
from .executor import run_tests
from .models import TestGenerationSession, RoundResult, TestedCodeUnit
from .reward import compute_reward

logger = logging.getLogger(__name__)


class VerificationManager:
    def __init__(self, llm, tracker, oracle: str = "crash", total_rounds: int = 5):
        self.generator = TestGenerator(llm, tracker=tracker)
        self.oracle = oracle
        self.total_rounds = total_rounds
        self._session_registry: Dict[str, TestGenerationSession] = {}

    def get_session_data(self) -> list[dict]:
        """Formats sessions for the summary report and CLI output."""
        session_data = []
        for session in self._session_registry.values():
            data = dataclasses.asdict(session)
            data["function"] = session.function_name
            data["final_coverage"] = session.final_coverage
            data["final_bugs"] = session.final_bugs
            data["learning_curve"] = session.learning_curve
            session_data.append(data)
        return session_data

    def verify(
        self,
        repaired_unit: RepairedCodeUnit,
        persist_dir: Optional[Path] = None,
        on_function_complete: Optional[Callable] = None,
    ) -> TestedCodeUnit:
        """Run test generation once per function (Option A: single pass per QALLM round).

        After each function completes:
          1. Saves test code + session JSON immediately to persist_dir
          2. Calls on_function_complete callback (for real-time UI updates)

        The multi-round learning happens at the orchestrator level:
        code improves via repair between QALLM rounds, not via test gen iteration.
        """
        unit = repaired_unit.repaired_code_unit
        source, path = unit.source_code, unit.original_path

        functions = extract_functions_from_source(source, str(path))
        unit_sessions = []

        for func_idx, func in enumerate(functions):
            session_key = f"{path.absolute()}::{func.name}"
            session = self._session_registry.get(session_key)
            if not session:
                session = TestGenerationSession(
                    function_name=func.name,
                    source_code=source,
                    oracle=self.oracle,
                    model=self.generator.llm.name(),
                    total_rounds=self.total_rounds
                )
                self._session_registry[session_key] = session

            module_name = f"source_{path.stem}_c{unit.cell_index}"

            logger.info(
                "Verifying %s [%d/%d]",
                func.name, func_idx + 1, len(functions),
            )

            # Generate tests (single pass per QALLM round)
            generated = self.generator.generate(func, module_name=module_name, existing_session=session)

            if generated.is_valid:
                execution = run_tests(source, generated.test_code, f"{module_name}.py", path)
            else:
                execution = ExecutionResult(
                    execution_error=f"Skipped: {generated.generation_error or 'invalid test code'}"
                )

            reward = compute_reward(execution, session.final_coverage)

            session.rounds.append(RoundResult(
                round_number=len(session.rounds) + 1,
                generated_test=generated, execution=execution, reward=reward,
                cumulative_coverage=max(session.final_coverage or 0.0,
                                        execution.coverage_percent or 0.0) if execution else 0.0,
                cumulative_bugs=session.final_bugs + (execution.bugs_found if execution else 0)
            ))

            logger.info(
                "  %s: reward=%.2f, coverage=%.1f%%, bugs=%d, valid=%s",
                func.name, reward.total,
                execution.coverage_percent or 0.0,
                execution.bugs_found if execution else 0,
                generated.is_valid,
            )

            # Incremental persistence: save immediately after each function
            if persist_dir:
                self._save_function_artifacts(session, func, persist_dir, path.stem)

            # Callback for real-time updates (e.g. WebSocket, progress bar)
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
