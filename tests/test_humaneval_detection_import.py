"""Detection harness must satisfy QALLM tests' own import lines.

QALLM's harvested tests import the function under test from a module name of
the form source_<unit>_c0. The detection harness previously wrote the target
only as <entry_point>_module.py, so every QALLM test errored at import and
bug_was_detected returned False uniformly (492/492 in the 2026-07-09 run).
These tests pin that the target is also written under the module name the test
imports from, so detection reflects test outcomes, not import failures.
"""
from __future__ import annotations

from qallm.experiments.humaneval_metrics import (
    bug_was_detected,
    run_tests_against_source,
)

BUGGY = "def add(a, b):\n    return a - b\n"
CANON = "def add(a, b):\n    return a + b\n"
QALLM_TEST = (
    "from source_nb_add_c0 import add\n"
    "def test_add():\n"
    "    assert add(2, 3) == 5\n"
)


def test_qallm_style_import_is_satisfied() -> None:
    passed, out = run_tests_against_source(QALLM_TEST, CANON, "add")
    assert passed, out


def test_detection_true_for_discriminating_qallm_test() -> None:
    assert bug_was_detected(
        qallm_test_code=QALLM_TEST,
        buggy_source=BUGGY,
        canonical_source=CANON,
        entry_point="add",
    ) is True


def test_detection_false_for_vacuous_test() -> None:
    vacuous = "from source_nb_add_c0 import add\ndef test_t():\n    assert True\n"
    assert bug_was_detected(
        qallm_test_code=vacuous,
        buggy_source=BUGGY,
        canonical_source=CANON,
        entry_point="add",
    ) is False
