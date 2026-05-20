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
    build_crash_oracle_prompt,
    build_metamorphic_oracle_prompt,
    build_property_oracle_prompt,
    build_feedback_prompt
)
from qallm.verification.sandbox import CodeExtractor

logger = logging.getLogger(__name__)

PROMPT_BUILDERS = {
    "crash": build_crash_oracle_prompt,
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
            logger.info("Generating feedback-based tests for %s (Round %d)",
                        func.name, len(existing_session.rounds) + 1)

            user_prompt = build_feedback_prompt(
                func=func,
                previous_test_code=last_round.generated_test.test_code,
                execution=last_round.execution,
                reward=last_round.reward,
                round_number=len(existing_session.rounds) + 1,
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
        )