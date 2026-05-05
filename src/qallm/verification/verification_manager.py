import dataclasses
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Dict

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
        """Formats sessions for the summary report and CLI output[cite: 43]."""
        session_data = []
        for session in self._session_registry.values():
            # Get raw fields[cite: 43]
            data = dataclasses.asdict(session)

            # Inject calculated properties and map keys for CLI/Web compatibility
            data["function"] = session.function_name
            data["final_coverage"] = session.final_coverage
            data["final_bugs"] = session.final_bugs
            data["learning_curve"] = session.learning_curve

            session_data.append(data)
        return session_data

    def verify(self, repaired_unit: RepairedCodeUnit) -> TestedCodeUnit:
        unit = repaired_unit.repaired_code_unit
        source, path = unit.source_code, unit.original_path

        functions = extract_functions_from_source(source, str(path))
        unit_sessions = []

        for func in functions:
            # Use full path to avoid filename collisions
            # FIX: Use absolute path to prevent session collisions across different files
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

            # 3. Incremental Generation[cite: 30]
            module_name = f"source_{path.stem}_c{unit.cell_index}"
            generated = self.generator.generate(func, module_name=module_name, existing_session=session)

            # 4. Isolated Execution: Never return None[cite: 28, 31]
            if generated.is_valid:
                execution = run_tests(source, generated.test_code, f"{module_name}.py", path)
            else:
                # Create a result object that captures the generation error
                execution = ExecutionResult(
                    execution_error=f"Skipped: {generated.generation_error or 'invalid test code'}"
                )

            # 5. RL Feedback: compute_reward now always gets an object[cite: 28]
            reward = compute_reward(execution, session.final_coverage)

            session.rounds.append(RoundResult(
                round_number=len(session.rounds) + 1,
                generated_test=generated, execution=execution, reward=reward,
                cumulative_coverage=max(session.final_coverage or 0.0,
                                        execution.coverage_percent or 0.0) if execution else 0.0,
                cumulative_bugs=session.final_bugs + (execution.bugs_found if execution else 0)
            ))
            unit_sessions.append(session)

        return TestedCodeUnit(repaired_unit=repaired_unit, sessions=unit_sessions)


def save_session(session: TestGenerationSession, output_path: Path) -> None:
    """Persist a verification session as JSON for reproducibility.

    Includes computed properties (final_coverage, final_bugs, learning_curve)
    which are @property methods not captured by dataclasses.asdict().
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(session)
    # Inject computed properties that asdict() skips
    data["final_coverage"] = session.final_coverage
    data["final_bugs"] = session.final_bugs
    data["learning_curve"] = session.learning_curve
    data["reward_per_round"] = session.reward_per_round
    output_path.write_text(
        json.dumps(data, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("Session saved to %s", output_path)