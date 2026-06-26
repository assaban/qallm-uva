"""Radon normalizer must tolerate error strings in place of metrics.

Radon can emit a string (an error message) instead of the complexity list or
maintainability dict when it cannot analyse a unit. A naive block.get then
raised 'str' object has no attribute 'get', which escaped the normalizer and
aborted the whole notebook (the ENVRI notebook-loss bug, second source).
"""
from __future__ import annotations

from qallm.analysis.normalization.radon_normalizer import RadonNormalizer


class _Raw:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.artifact = "source.py"


def _run(stdout: str):
    return RadonNormalizer().normalize(_Raw(stdout))


def test_complexity_error_string_does_not_raise() -> None:
    assert _run('{"complexity": "Error: invalid syntax"}') == []


def test_non_dict_block_skipped_rest_kept() -> None:
    out = '{"complexity": ["oops", {"complexity": 8, "lineno": 3, "name": "f"}]}'
    findings = _run(out)
    assert len(findings) == 1  # the good block survives


def test_maintainability_string_does_not_raise() -> None:
    assert _run('{"maintainability": "err"}') == []


def test_well_formed_still_works() -> None:
    out = ('{"complexity":[{"complexity":9,"lineno":2,"name":"g","rank":"C"}],'
           '"maintainability":{"mi":40}}')
    findings = _run(out)
    assert len(findings) == 2  # one COMPLEXITY, one MAINTAINABILITY
