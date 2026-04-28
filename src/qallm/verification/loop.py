"""RL feedback loop for iterative test improvement (T-017).

This module orchestrates the core thesis contribution: the iterative
cycle of generate → execute → score → feedback that drives test quality
improvement across multiple rounds.

The loop works as follows:
    Round 1: Generate tests using the crash oracle prompt (one-shot)
    Round 2+: Generate tests using a feedback prompt that includes
              the previous round's execution results, coverage gaps,
              and reward breakdown.

Each round produces a RoundResult containing the generated test,
execution outcome, and reward score. The complete session is stored
as a TestGenerationSession for reproducibility and analysis.

Usage:
    loop = TestGenerationLoop(llm, rounds=5)
    session = loop.run(function_info, source_code)
    print(session.learning_curve)  # [0.5, 1.2, 2.1, 2.8, 3.5]
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

from qallm.llm.base import LLMModel, TokenTracker
from qallm.verification.executor import run_tests
from qallm.verification.generator import TestGenerator
from qallm.verification.models import (
    ExecutionResult,
    FunctionInfo,
    OracleType,
    RewardBreakdown,
    RoundResult,
    TestGenerationSession,
)
from qallm.verification.prompts import SYSTEM_PROMPT, build_feedback_prompt
from qallm.verification.reward import RewardWeights, compute_reward

logger = logging.getLogger(__name__)


class TestGenerationLoop:
    __test__ = False
    """Orchestrates the RL-guided test generation feedback loop.

    The loop runs N rounds of: generate → execute → score → feedback.
    Each round uses the previous round's results to guide the LLM
    toward generating better tests.

    Args:
        llm: The LLM model to use for test generation.
        rounds: Number of feedback rounds (default: 5, max recommended: 10).
        oracle: Oracle type for the initial prompt.
        weights: Reward function weights.
        timeout: Test execution timeout in seconds.
        tracker: Token usage tracker. Created automatically if not provided.
    """

    def __init__(
        self,
        llm: LLMModel,
        rounds: int = 5,
        oracle: OracleType = "crash",
        weights: RewardWeights | None = None,
        timeout: int = 60,
        tracker: TokenTracker | None = None,
    ) -> None:
        self.llm = llm
        self.rounds = max(1, min(rounds, 20))  # clamp to 1..20
        self.oracle = oracle
        self.weights = weights
        self.timeout = timeout
        self.tracker = tracker or TokenTracker(budget=100_000)

    def run(
        self,
        func: FunctionInfo,
        source_code: str,
        module_name: str = "source_module",
        persist_dir: Path | None = None,
        source_origin: Path | None = None,
    ) -> TestGenerationSession:
        """Execute the full RL verification loop for a single function.

        Args:
            func: The function to generate tests for.
            source_code: Complete source module containing the function.
            module_name: Module name for the import statement in generated tests.
            persist_dir: If set, save each round's generated test code here.

        Returns:
            TestGenerationSession with all round results and aggregate metrics.
        """
        if persist_dir:
            persist_dir.mkdir(parents=True, exist_ok=True)

        session = TestGenerationSession(
            function_name=func.name,
            source_code=source_code,
            oracle=self.oracle,
            model=self.llm.name(),
            total_rounds=self.rounds,
        )

        generator = TestGenerator(self.llm, tracker=self.tracker)
        best_coverage: float | None = None
        cumulative_bugs: int = 0
        prev_execution: ExecutionResult | None = None
        prev_reward: RewardBreakdown | None = None
        prev_test_code: str = ""

        for round_num in range(1, self.rounds + 1):
            logger.info(
                "=== Round %d/%d for %s ===",
                round_num,
                self.rounds,
                func.name,
            )

            # Step 1: Generate tests
            if round_num == 1:
                # First round: use the standard oracle prompt
                generated = generator.generate(func, oracle=self.oracle, module_name=module_name)
            else:
                # Subsequent rounds: use feedback prompt with previous results
                feedback_prompt = build_feedback_prompt(
                    func=func,
                    previous_test_code=prev_test_code,
                    execution=prev_execution,
                    reward=prev_reward,
                    round_number=round_num,
                )
                # Call LLM directly with feedback prompt
                from qallm.verification.generator import _fix_source_import, _validate_test_code
                from qallm.verification.sandbox import CodeExtractor
                from qallm.verification.models import GeneratedTest

                resp = self.llm.chat(SYSTEM_PROMPT, feedback_prompt, self.tracker)

                if resp.error:
                    generated = GeneratedTest(
                        function_name=func.name,
                        oracle=self.oracle,
                        test_code="",
                        is_valid=False,
                        generation_error=resp.error,
                        model=resp.model,
                        provider=resp.provider,
                        input_tokens=resp.input_tokens,
                        output_tokens=resp.output_tokens,
                    )
                else:
                    raw_code, _ = CodeExtractor.extract(resp.content)
                    test_code = _fix_source_import(raw_code, module_name)
                    is_valid, validation_error = _validate_test_code(test_code)

                    generated = GeneratedTest(
                        function_name=func.name,
                        oracle=self.oracle,
                        test_code=test_code,
                        is_valid=is_valid,
                        generation_error=validation_error,
                        model=resp.model,
                        provider=resp.provider,
                        input_tokens=resp.input_tokens,
                        output_tokens=resp.output_tokens,
                    )

            # Step 2: Execute tests
            if generated.is_valid:
                execution = run_tests(
                    source_code=source_code,
                    test_code=generated.test_code,
                    source_filename=f"{module_name}.py",
                    source_origin=source_origin,
                    timeout=self.timeout,
                )
            else:
                execution = ExecutionResult(
                    execution_error=f"Skipped: invalid test code ({generated.generation_error})",
                )

            # Step 3: Score with reward function
            reward = compute_reward(
                execution=execution,
                previous_coverage=best_coverage,
                weights=self.weights,
            )

            # Step 4: Update cumulative metrics
            current_cov = execution.coverage_percent or 0.0
            if best_coverage is None or current_cov > best_coverage:
                best_coverage = current_cov

            cumulative_bugs += execution.bugs_found

            # Store round result
            round_result = RoundResult(
                round_number=round_num,
                generated_test=generated,
                execution=execution,
                reward=reward,
                cumulative_coverage=best_coverage,
                cumulative_bugs=cumulative_bugs,
            )
            session.rounds.append(round_result)

            # Persist generated test code to session folder
            if persist_dir and generated.is_valid and generated.test_code:
                test_filename = f"{func.name}_round_{round_num:02d}.py"
                header = (
                    f"# Generated by QALLM TestGenerationLoop\n"
                    f"# Source file: {func.filepath}\n"
                    f"# Function: {func.name} (line {func.lineno})\n"
                    f"# Oracle: {self.oracle} | Round: {round_num} | Model: {self.llm.name()}\n\n"
                )
                (persist_dir / test_filename).write_text(header + generated.test_code, encoding="utf-8")

            # Track tokens
            session.total_input_tokens += generated.input_tokens
            session.total_output_tokens += generated.output_tokens

            logger.info(
                "Round %d: reward=%.2f, coverage=%.1f%%, bugs=%d, valid=%s",
                round_num,
                reward.total,
                current_cov,
                execution.bugs_found,
                generated.is_valid,
            )

            # Step 5: Prepare feedback for next round
            prev_execution = execution
            prev_reward = reward
            prev_test_code = generated.test_code

            # Early stop: if coverage is 100% and bugs are found, no need to continue
            if best_coverage is not None and best_coverage >= 100.0 and cumulative_bugs > 0:
                logger.info("Early stop: 100%% coverage and %d bugs found", cumulative_bugs)
                break

        logger.info(
            "Verification complete for %s: %d rounds, final coverage=%.1f%%, total bugs=%d",
            func.name,
            len(session.rounds),
            best_coverage or 0.0,
            cumulative_bugs,
        )

        return session


def save_session(session: TestGenerationSession, output_path: Path) -> None:
    """Persist a verification session as JSON for reproducibility."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(asdict(session), indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("Session saved to %s", output_path)
