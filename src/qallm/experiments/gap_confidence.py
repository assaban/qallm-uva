"""Attach mutation-based confidence to verification-gap findings.

After a gap report names the functions with an execution-only bug (the gap),
this reads each such function's source and its round-0 generated test suite from
the on-disk artefacts and runs the mutation scorer over them. The result is a
confidence label per gap function (high/medium/low/unknown) and an aggregate
distribution, so a reported gap can be qualified by how sensitive the oracle
that found it actually is.

Like confirm/verify, this needs the round-0 artefacts on disk (source.py and
tests/), so it requires full retention. It is opt-in (the runner enables it via
config), and it scores only the gap functions, where confidence matters, not
every function, so the cost stays proportional to the number of findings.
"""

from __future__ import annotations

import logging
import os

from qallm.verification.mutation_score import score_oracle

logger = logging.getLogger(__name__)


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def _baseline_dir(report_dir: str) -> str | None:
    """The round-0 lineage directory, tolerating both naming conventions.

    The reporter writes round_00 (round_{n:02d}); some older paths used
    round_0. Try both so this works regardless of which produced the run.
    """
    for name in ("round_00", "round_0"):
        candidate = os.path.join(report_dir, "lineage", name)
        if os.path.isdir(candidate):
            return candidate
    return None


def _test_code_for(unit_dir: str, func_name: str) -> str | None:
    """The generated test suite for one function in a unit dir.

    Tests are written per function as tests/test_<func>.py. If that exact file
    is absent (naming variance), fall back to concatenating every test file in
    the unit that mentions the function, so a renamed file still contributes.
    """
    tests_dir = os.path.join(unit_dir, "tests")
    if not os.path.isdir(tests_dir):
        return None
    exact = os.path.join(tests_dir, f"test_{func_name}.py")
    code = _read_text(exact)
    if code:
        return code
    parts = []
    for name in sorted(os.listdir(tests_dir)):
        if not name.endswith(".py"):
            continue
        text = _read_text(os.path.join(tests_dir, name))
        if text and func_name in text:
            parts.append(text)
    return "\n\n".join(parts) if parts else None


def _functions_in(source: str) -> set[str]:
    """Names of functions defined at any level in the source."""
    import ast
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return {
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _final_sources_map(report_dir: str) -> dict[str, str]:
    """Map unit segment -> repaired (final accepted) source, highest round.

    Reused from the confirm/verify logic. The repaired source is the version a
    sound suite should pass, which is the right base for mutation scoring of a
    gap function (whose round-0 source is the buggy code the suite catches).
    """
    finals: dict[str, str] = {}
    lineage = os.path.join(report_dir, "lineage")
    if not os.path.isdir(lineage):
        return finals
    round_dirs = []
    for round_name in os.listdir(lineage):
        if not round_name.startswith("round_"):
            continue
        try:
            round_dirs.append((int(round_name.replace("round_", "")), round_name))
        except ValueError:
            continue
    for _, round_name in sorted(round_dirs):  # ascending: later overwrites earlier
        round_path = os.path.join(lineage, round_name)
        for unit_seg in os.listdir(round_path):
            src = _read_text(os.path.join(round_path, unit_seg, "source.py"))
            if src:
                finals[unit_seg] = src
    return finals


def _scoring_source(original: str, repaired: str | None,
                    func_name: str, test_code: str) -> str:
    """Pick the source to mutate so confidence measures oracle sensitivity.

    Mutation testing assumes the base code is correct. For a gap function the
    original is buggy (the suite fails on it), so we prefer a version the suite
    PASSES: the repaired source if it exists and the suite passes on it. If the
    repaired source is absent or the suite does not pass on it either, fall back
    to the original (score_oracle's own baseline handling then applies).
    """
    if not repaired or func_name not in _functions_in(repaired):
        return original
    try:
        from qallm.verification.executor import run_tests
        r = run_tests(repaired, test_code, "source_module.py")
        if r.passed > 0 and r.failed == 0:
            return repaired
    except Exception:  # any execution issue: fall back to the original
        pass
    return original


def score_gap_confidence_from_dir(
    report_dir: str,
    gap_functions: list[str] | None = None,
    max_per_operator: int = 3,
) -> dict:
    """Mutation-score the oracle for each gap function under report_dir.

    Args:
        report_dir: the session report directory.
        gap_functions: restrict scoring to these function names (the
            execution-only functions). When None, every function with a test
            suite is scored.
        max_per_operator: mutant bound passed to the scorer.

    Returns a dict with per-function confidence and an aggregate distribution:
        {
          "per_function": {func: {mutation_score, confidence, killed, ...}},
          "distribution": {"high": n, "medium": n, "low": n, "unknown": n},
          "scored": n,
        }
    """
    out: dict = {"per_function": {}, "distribution": {}, "scored": 0}
    base = _baseline_dir(report_dir)
    if base is None:
        logger.info("No round-0 artefacts under %s; skipping gap confidence.",
                    report_dir)
        return out

    want = set(gap_functions) if gap_functions is not None else None
    dist = {"high": 0, "medium": 0, "low": 0, "unknown": 0}

    # Collect (source, tests_dir) per unit once, so a gap function can be scored
    # against the unit whose source ACTUALLY defines it. A function is scored at
    # most once even if its name appears in several units' test files.
    units: list[tuple[str, str]] = []
    for unit_seg in sorted(os.listdir(base)):
        unit_dir = os.path.join(base, unit_seg)
        if not os.path.isdir(unit_dir):
            continue
        source = _read_text(os.path.join(unit_dir, "source.py"))
        tests_dir = os.path.join(unit_dir, "tests")
        if source and os.path.isdir(tests_dir):
            units.append((source, unit_dir))

    # For a GAP function the round-0 source is, by definition, the buggy code
    # the suite was written to catch, so the suite FAILS on it. Mutation testing
    # assumes the base code is correct (inject a fault, see if the suite catches
    # it), so scoring against the buggy original makes every mutant look
    # not-viable and the function scores "unknown". To measure the oracle's
    # sensitivity properly we score against a version the suite PASSES: the
    # repaired source from a later lineage round if one exists, else the
    # original. _scoring_source picks that per function.
    finals = _final_sources_map(report_dir)

    scored_funcs: set[str] = set()
    for source, unit_dir in units:
        defined = _functions_in(source)
        unit_seg = os.path.basename(unit_dir.rstrip(os.sep))
        repaired = finals.get(unit_seg)
        for name in sorted(os.listdir(os.path.join(unit_dir, "tests"))):
            if not (name.startswith("test_") and name.endswith(".py")):
                continue
            func_name = name[len("test_"):-len(".py")]
            if want is not None and func_name not in want:
                continue
            if func_name in scored_funcs:
                continue
            # Only score against a unit whose source defines this function;
            # otherwise generate_mutants finds nothing and we would wrongly
            # record "unknown" for a function that simply lives elsewhere.
            if func_name not in defined:
                continue
            test_code = _test_code_for(unit_dir, func_name)
            if not test_code:
                logger.debug("No test code for %s in %s; skipping.",
                             func_name, unit_dir)
                continue
            base_source = _scoring_source(source, repaired, func_name, test_code)
            score = score_oracle(
                base_source, func_name, test_code,
                max_per_operator=max_per_operator,
            )
            out["per_function"][func_name] = score.to_dict()
            dist[score.confidence] = dist.get(score.confidence, 0) + 1
            out["scored"] += 1
            scored_funcs.add(func_name)

    # A gap function we never found in any unit's source is unresolved, not
    # "unknown confidence"; report it separately so the distribution is not
    # polluted by lookup misses.
    if want is not None:
        unresolved = sorted(want - scored_funcs)
        if unresolved:
            out["unresolved"] = unresolved
            logger.info("Gap functions not found in artefacts: %s", unresolved)

    out["distribution"] = dist
    logger.info("Gap confidence over %s: %d scored, distribution=%s",
                report_dir, out["scored"], dist)
    return out
