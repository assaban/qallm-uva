"""LLM-based test generator.

Generates pytest test cases for Python functions by calling an LLM
with oracle-specific prompts. Uses CodeExtractor for robust parsing
of LLM output.
"""

from __future__ import annotations

import logging
import re

from qallm.llm.base import LLMModel, TokenTracker
from qallm.verification.models import FunctionInfo, GeneratedTest, OracleType, TestGenerationSession
from qallm.verification.prompts import (
    SYSTEM_PROMPT,
    build_correctness_oracle_prompt,
    build_crash_oracle_prompt,
    build_metamorphic_oracle_prompt,
    build_property_oracle_prompt,
    build_feedback_prompt
)
from qallm.verification.sandbox import CodeExtractor
from qallm.verification.test_validator import (
    strip_unsatisfied_fixture_tests,
    strip_incoherent_oracle_tests,
)

logger = logging.getLogger(__name__)

PROMPT_BUILDERS = {
    "crash": build_crash_oracle_prompt,
    "correctness": build_correctness_oracle_prompt,
    "property": build_property_oracle_prompt,
    "metamorphic": build_metamorphic_oracle_prompt,
}


def _fix_source_import(test_code: str, module_name: str) -> str:
    """Replace 'source_module' placeholder with the actual module name."""
    return test_code.replace("source_module", module_name)


def _validate_test_code(code: str) -> tuple[bool, str | None]:
    """Check if the generated code compiles and contains test functions."""
    if not code.strip():
        return False, "Empty test code"
    try:
        compile(code, "<generated_test>", "exec")
    except SyntaxError as exc:
        return False, f"Syntax error: {exc}"
    if not re.search(r"^def test_", code, re.MULTILINE):
        return False, "No test functions found (expected functions starting with 'test_')"
    return True, None


class TestGenerator:
    __test__ = False

    def __init__(self, llm: LLMModel, tracker: TokenTracker | None = None) -> None:
        self.llm = llm
        self.tracker = tracker or TokenTracker(budget=50_000)

    def generate(
            self,
            func: FunctionInfo,
            oracle: OracleType = "crash",
            module_name: str = "source_module",
            existing_session: TestGenerationSession | None = None
    ) -> GeneratedTest:
        """
        Generates pytest test cases. If an existing_session with previous rounds
        is provided, it switches to a feedback-driven prompt.
        """
        # 1. Select the appropriate prompt builder based on session state
        if existing_session and len(existing_session.rounds) > 0:
            last_round = existing_session.rounds[-1]
            # Label by the pipeline round being verified (the count of prior
            # generations), so the log matches the orchestrator's "Round N"
            # instead of being one ahead.
            gen_round = len(existing_session.rounds)
            logger.info("Generating feedback-based tests for %s (round %d)",
                        func.name, gen_round)

            user_prompt = build_feedback_prompt(
                func=func,
                previous_test_code=last_round.generated_test.test_code,
                execution=last_round.execution,
                reward=last_round.reward,
                round_number=gen_round + 1,
            )
        else:
            builder = PROMPT_BUILDERS.get(oracle)
            if builder is None:
                return GeneratedTest(
                    function_name=func.name, oracle=oracle, test_code="",
                    is_valid=False, generation_error=f"Unknown oracle type: {oracle}",
                )
            logger.info("Generating initial %s tests for %s", oracle, func.name)
            user_prompt = builder(func)

        # 2. Call the LLM[cite: 39]
        resp = self.llm.chat(SYSTEM_PROMPT, user_prompt, self.tracker)

        if resp.error:
            logger.warning("LLM error generating tests for %s: %s", func.name, resp.error)
            return GeneratedTest(
                function_name=func.name, oracle=oracle, test_code="",
                is_valid=False, generation_error=resp.error,
                model=resp.model, provider=resp.provider,
                input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
            )

        # 3. Extract and sanitize the code
        extracted_code, strategy = CodeExtractor.extract(resp.content)
        logger.info("Extraction strategy: %s", strategy)

        # Apply module name fixing and validation[cite: 39]
        test_code = _fix_source_import(extracted_code, module_name)
        is_valid, validation_error = _validate_test_code(test_code)

        # Drop tests that request fixtures nothing provides: they would
        # error during pytest setup and never run, contributing no signal
        # while inflating the error count. Keep the valid tests.
        discarded: list[str] = []
        if is_valid:
            stripped_code, discarded = strip_unsatisfied_fixture_tests(test_code)
            if discarded:
                logger.warning(
                    "Discarded %d test(s) for %s requesting undefined "
                    "fixtures: %s",
                    len(discarded), func.name, ", ".join(discarded),
                )
                test_code = stripped_code
                # Re-validate: if stripping removed every test, the result
                # is no longer a usable suite.
                is_valid, validation_error = _validate_test_code(test_code)
                if not is_valid:
                    validation_error = (
                        "All generated tests requested undefined fixtures "
                        f"({', '.join(discarded)}); nothing left to run."
                    )

        # Drop tests whose oracle is evaluated at a different input than the
        # function under test: such a failure is an artifact of the test, not
        # a defect in the code, so letting it run would record a false bug and
        # undermine the validity of the execution-based verdict. Conservative:
        # only unambiguous constant-vs-constant mismatches are removed.
        if is_valid:
            stripped_code, incoherent = strip_incoherent_oracle_tests(
                test_code, func.name
            )
            if incoherent:
                logger.warning(
                    "Discarded %d test(s) for %s with an oracle evaluated at a "
                    "different input than the call (false-bug risk): %s",
                    len(incoherent), func.name, ", ".join(incoherent),
                )
                test_code = stripped_code
                is_valid, validation_error = _validate_test_code(test_code)
                if not is_valid:
                    validation_error = (
                        "All generated tests had incoherent oracles "
                        f"({', '.join(incoherent)}); nothing left to run."
                    )

        if not is_valid:
            logger.warning("Generated tests for %s are invalid: %s", func.name, validation_error)

        return GeneratedTest(
            function_name=func.name,
            oracle=oracle,
            test_code=test_code,
            is_valid=is_valid,
            generation_error=validation_error,
            model=resp.model,
            provider=resp.provider,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            discarded_tests=discarded,
        )