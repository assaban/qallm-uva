"""Score an oracle's discriminating power by mutation testing.

Given a function, a test suite generated for it, and a way to run tests, this
injects mutants of the function and measures how many the suite catches. The
result is a mutation score (killed / viable) and a derived confidence label for
any verification-gap finding the suite produced.

Why this matters for the thesis: it converts "an LLM-generated test failed, so
the code has a bug" into "this test suite killed 7 of 8 injected faults, so it
is a sensitive detector, and its finding is high-confidence." A suite that kills
no mutants cannot be trusted to have found a real defect; its finding is flagged
low-confidence rather than reported as a gap. This is a positive, quantitative
soundness check on top of the existing negative guards (incoherent-oracle
filter, baseline gate), and it directly answers the reviewer question "how do
you know your execution-found bugs are real?".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from qallm.verification.executor import run_tests
from qallm.verification.mutation import Mutant, generate_mutants

logger = logging.getLogger(__name__)


@dataclass
class MutationScore:
    """The outcome of mutation-testing a suite against one function."""
    function_name: str
    total_mutants: int = 0
    killed: int = 0
    survived: int = 0
    not_viable: int = 0          # mutants that errored on every test (cannot run)
    killed_operators: dict = field(default_factory=dict)  # operator -> kill count
    surviving_examples: list = field(default_factory=list)  # descriptions

    @property
    def viable(self) -> int:
        return self.killed + self.survived

    @property
    def score(self) -> float | None:
        """Killed / viable. None when no viable mutant could be produced."""
        return (self.killed / self.viable) if self.viable else None

    @property
    def confidence(self) -> str:
        """A label for any gap finding this suite produced.

        high   the suite kills most injected faults -> sensitive detector
        medium partial discrimination
        low    the suite kills few/none -> its verdict is not trustworthy
        unknown no viable mutant (e.g. trivial function) -> cannot assess
        """
        s = self.score
        if s is None:
            return "unknown"
        if s >= 0.8:
            return "high"
        if s >= 0.5:
            return "medium"
        return "low"

    def to_dict(self) -> dict:
        return {
            "function": self.function_name,
            "total_mutants": self.total_mutants,
            "killed": self.killed,
            "survived": self.survived,
            "not_viable": self.not_viable,
            "viable": self.viable,
            "mutation_score": self.score,
            "confidence": self.confidence,
            "killed_by_operator": self.killed_operators,
            "surviving_examples": self.surviving_examples[:5],
        }


def _suite_kills(source: str, test_code: str, module_name: str) -> str:
    """Run the suite against one mutant. Returns 'killed', 'survived', or
    'not_viable'.

    A mutant is KILLED if at least one test fails (the suite detected the
    injected fault). It SURVIVED if every test passes (the suite missed it). It
    is NOT_VIABLE if every test errors (the mutant cannot even run, so it tells
    us nothing about discrimination, e.g. it broke an import the tests need).
    """
    result = run_tests(source, test_code, f"{module_name}.py")
    if result.failed > 0:
        return "killed"
    if result.passed > 0:
        return "survived"
    return "not_viable"


def score_oracle(
    source: str,
    func_name: str,
    test_code: str,
    module_name: str = "source_module",
    max_per_operator: int = 3,
) -> MutationScore:
    """Mutation-test ``test_code`` against ``func_name`` in ``source``.

    Generates mutants of the function, runs the suite against each, and
    aggregates kills. Cost is bounded by max_per_operator mutants per operator
    class. A suite that is empty or invalid trivially scores nothing.
    """
    score = MutationScore(function_name=func_name)
    if not test_code or not test_code.strip():
        return score

    mutants: list[Mutant] = generate_mutants(source, func_name, max_per_operator)
    score.total_mutants = len(mutants)
    if not mutants:
        return score

    for m in mutants:
        try:
            outcome = _suite_kills(m.source, test_code, module_name)
        except Exception as exc:  # a mutant that breaks execution entirely
            logger.debug("Mutant errored (%s): %s", m.description, exc)
            outcome = "not_viable"
        if outcome == "killed":
            score.killed += 1
            score.killed_operators[m.operator] = (
                score.killed_operators.get(m.operator, 0) + 1
            )
        elif outcome == "survived":
            score.survived += 1
            score.surviving_examples.append(f"[{m.operator}] {m.description}")
        else:
            score.not_viable += 1

    logger.info(
        "Mutation score for %s: %d/%d killed (score=%s, confidence=%s)",
        func_name, score.killed, score.viable,
        f"{score.score:.2f}" if score.score is not None else "n/a",
        score.confidence,
    )
    return score
