"""TruffleHog adapter must tolerate malformed findings.

A single finding with an unexpected schema (SourceMetadata or Data a string
rather than a dict) previously raised 'str' object has no attribute 'get',
which escaped the adapter and aborted the entire notebook. On the ENVRI corpus
this lost hundreds of notebooks. These tests pin that one bad finding is skipped
and the rest survive.
"""
from __future__ import annotations

from qallm.analysis.trufflehog_analyzer import TruffleHogAnalyzer


def _run(stdout: str) -> dict:
    analyzer = TruffleHogAnalyzer.__new__(TruffleHogAnalyzer)
    report: dict = {"issues": []}

    class _Raw:
        pass

    raw = _Raw()
    raw.stdout = stdout
    analyzer.map_result_to_report(report, raw)
    return report


def test_data_is_string_does_not_raise() -> None:
    line = '{"DetectorName":"AWS","Raw":"AKIA","SourceMetadata":{"Data":"oops"}}'
    report = _run(line)
    assert len(report["issues"]) == 1
    assert report["issues"][0]["line_number"] == 0


def test_source_metadata_is_string_does_not_raise() -> None:
    report = _run('{"SourceMetadata":"oops"}')
    assert len(report["issues"]) == 1


def test_well_formed_extracts_line() -> None:
    line = '{"DetectorName":"AWS","Raw":"x","SourceMetadata":{"Data":{"Filesystem":{"line":42}}}}'
    report = _run(line)
    assert report["issues"][0]["line_number"] == 42


def test_one_bad_line_does_not_drop_the_rest() -> None:
    bad = '{"SourceMetadata":{"Data":"oops"}}'
    good = '{"DetectorName":"AWS","Raw":"x","SourceMetadata":{"Data":{"Filesystem":{"line":7}}}}'
    report = _run(bad + "\n" + good)
    # both produce a finding; the bad one does not abort the loop
    assert len(report["issues"]) == 2
    assert any(i["line_number"] == 7 for i in report["issues"])


def test_non_object_line_skipped() -> None:
    report = _run('"just a string"')
    assert report["issues"] == []
