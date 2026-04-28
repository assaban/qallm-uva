"""Hypothesis property-based testing baseline for RQ1.

Strategy (a) from thesis Section 4.2: generates random inputs matching
type annotations with automatic shrinking. No LLM involved. This is
the non-trivial control group for the three-strategy comparison.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from qallm.verification.executor import run_tests
from qallm.verification.extractor import extract_functions_from_source
from qallm.verification.models import FunctionInfo, ExecutionResult

logger = logging.getLogger(__name__)

# Maps Python type annotation strings to Hypothesis strategies
TYPE_STRATEGY_MAP = {
    "int": "st.integers(min_value=-1000, max_value=1000)",
    "float": "st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6)",
    "str": "st.text(max_size=50)",
    "bool": "st.booleans()",
    "list": "st.lists(st.integers(), max_size=10)",
    "list[int]": "st.lists(st.integers(), max_size=10)",
    "list[float]": "st.lists(st.floats(allow_nan=False, allow_infinity=False), max_size=10)",
    "list[str]": "st.lists(st.text(max_size=20), max_size=10)",
    "dict": "st.dictionaries(st.text(max_size=10), st.integers(), max_size=5)",
    "tuple": "st.tuples(st.integers(), st.integers())",
    "None": "st.none()",
    "Optional[int]": "st.one_of(st.none(), st.integers())",
    "Optional[str]": "st.one_of(st.none(), st.text(max_size=50))",
}

# Fallback: when no type annotation exists, try all common types
FALLBACK_STRATEGY = "st.one_of(st.integers(), st.text(max_size=20), st.lists(st.integers(), max_size=5), st.none())"


def _resolve_strategy(annotation: str | None) -> str:
    """Convert a type annotation string to a Hypothesis strategy."""
    if annotation is None or annotation.strip() == "":
        return FALLBACK_STRATEGY
    clean = annotation.strip().replace(" ", "")
    return TYPE_STRATEGY_MAP.get(clean, FALLBACK_STRATEGY)


def generate_hypothesis_test(func: FunctionInfo, module_name: str = "source_module") -> str:
    """Generate a Hypothesis property-based test for a single function.

    The test uses @given to generate random typed inputs and asserts
    that the function does not crash (crash oracle). This matches the
    thesis definition: 'generates random inputs matching type annotations
    with automatic shrinking to find minimal failing cases.'
    """
    strategies = []
    params = []
    for arg_name, arg_type in func.args:
        if arg_name == "self":
            continue
        strategy = _resolve_strategy(arg_type)
        strategies.append(f"    {arg_name}={strategy},")
        params.append(arg_name)

    if not params:
        # Function takes no args (besides possibly self): just call it
        return f'''import pytest
from hypothesis import given, settings, HealthCheck
import hypothesis.strategies as st
from {module_name} import {func.name}

def test_{func.name}_callable():
    """Baseline: verify function is callable without crash."""
    try:
        {func.name}()
    except TypeError:
        pass  # Expected if function needs arguments we cannot infer
'''

    params_str = ", ".join(params)
    strategies_str = "\n".join(strategies)

    return f'''import pytest
from hypothesis import given, settings, HealthCheck
import hypothesis.strategies as st
from {module_name} import {func.name}

@given(
{strategies_str}
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_{func.name}_no_crash({params_str}):
    """Baseline crash oracle: function should not raise unhandled exceptions on typed inputs."""
    try:
        result = {func.name}({params_str})
    except (ValueError, TypeError, KeyError, IndexError, ZeroDivisionError):
        pass  # Known exception types are acceptable defensive behavior
    # If it raises anything else (e.g. AttributeError, RuntimeError), the test fails


@given(
{strategies_str}
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_{func.name}_deterministic({params_str}):
    """Baseline property oracle: same input should produce same output."""
    try:
        result1 = {func.name}({params_str})
        result2 = {func.name}({params_str})
        assert result1 == result2, "Function is non-deterministic on identical inputs"
    except (ValueError, TypeError, KeyError, IndexError, ZeroDivisionError):
        pass  # If it raises on this input, both calls should raise
'''


def run_hypothesis_baseline(
    source_code: str,
    source_filename: str = "source_module.py",
    source_origin: Path | None = None,
) -> list[dict]:
    """Run Hypothesis baseline on all functions in a source file.

    Returns a list of results, one per function, in the same shape
    as a single-round TestGenerationSession for easy comparison.
    """
    module_name = source_filename.removesuffix(".py")
    functions = extract_functions_from_source(source_code, source_filename)

    results = []
    for func in functions:
        test_code = generate_hypothesis_test(func, module_name)

        execution = run_tests(
            source_code=source_code,
            test_code=test_code,
            source_filename=source_filename,
            source_origin=source_origin,
            timeout=120,  # Hypothesis needs more time for shrinking
        )

        results.append({
            "function": func.name,
            "strategy": "hypothesis",
            "test_code": test_code,
            "passed": execution.passed,
            "failed": execution.failed,
            "errors": execution.errors,
            "coverage": execution.coverage_percent,
            "bugs_found": execution.bugs_found,
            "execution_error": execution.execution_error,
        })

        logger.info(
            "  Hypothesis: %s passed=%d failed=%d errors=%d cov=%s",
            func.name, execution.passed, execution.failed,
            execution.errors, execution.coverage_percent,
        )

    return results