"""Pinning tests for the normalised finding shape.

The verification gap depends on the findings these adapters produce. If a tool's
output format shifts, or a normaliser's mapping changes, the gap metric changes
silently. These tests pin the contract: given known raw tool output, assert the
exact normalised Finding/issue shape (tool, type, severity, line, rule).
"""

import json

from qallm.analysis.analysis_model import RawToolResult
from qallm.analysis.normalization.radon_normalizer import RadonNormalizer
from qallm.analysis.util import get_snippet


# --------------------------------------------------------------------------
# Radon normaliser: complexity (CC) and maintainability (MI)
# --------------------------------------------------------------------------

def _radon_raw(payload: dict, artifact: str = "source.py") -> RawToolResult:
    return RawToolResult(
        tool="radon", exit_code=0,
        stdout=json.dumps(payload), stderr="", artifact=artifact,
    )


def test_radon_cc_above_threshold_becomes_finding():
    raw = _radon_raw({"complexity": [
        {"complexity": 7, "lineno": 3, "name": "f", "rank": "B"},
    ]})
    out = RadonNormalizer().normalize(raw)
    assert len(out) == 1
    f = out[0]
    assert f.tool == "radon"
    assert f.type == "COMPLEXITY"
    assert f.rule_id == "CC"
    assert f.line == 3
    assert f.extra["complexity"] == 7


def test_radon_cc_at_or_below_threshold_is_ignored():
    # threshold is > 5, so 5 must not produce a finding
    raw = _radon_raw({"complexity": [
        {"complexity": 5, "lineno": 1, "name": "small"},
    ]})
    assert RadonNormalizer().normalize(raw) == []


def test_radon_cc_severity_bands():
    norm = RadonNormalizer()
    assert norm._severity_from_cc(7) == "MEDIUM"
    assert norm._severity_from_cc(15) == "HIGH"
    assert norm._severity_from_cc(20) == "CRITICAL"


def test_radon_mi_below_threshold_becomes_finding():
    raw = _radon_raw({"maintainability": {"mi": 42.5, "rank": "B"}})
    out = RadonNormalizer().normalize(raw)
    assert len(out) == 1
    assert out[0].type == "MAINTAINABILITY"
    assert out[0].rule_id == "MI"
    assert out[0].line == 1
    assert out[0].extra["mi_score"] == 42.5


def test_radon_mi_at_or_above_threshold_is_ignored():
    raw = _radon_raw({"maintainability": {"mi": 70}})
    assert RadonNormalizer().normalize(raw) == []


def test_radon_mi_severity_bands():
    norm = RadonNormalizer()
    assert norm._severity_from_mi(39) == "CRITICAL"
    assert norm._severity_from_mi(50) == "HIGH"
    assert norm._severity_from_mi(65) == "MEDIUM"


def test_radon_combined_cc_and_mi():
    raw = _radon_raw({
        "complexity": [{"complexity": 25, "lineno": 10, "name": "big"}],
        "maintainability": {"mi": 30},
    })
    out = RadonNormalizer().normalize(raw)
    types = sorted(f.type for f in out)
    assert types == ["COMPLEXITY", "MAINTAINABILITY"]
    cc = next(f for f in out if f.type == "COMPLEXITY")
    assert cc.severity == "CRITICAL"


def test_radon_empty_stdout_is_empty():
    assert RadonNormalizer().normalize(
        RawToolResult("radon", 0, "", "", "source.py")) == []


def test_radon_malformed_json_is_empty():
    assert RadonNormalizer().normalize(
        RawToolResult("radon", 0, "{not json", "", "source.py")) == []


# --------------------------------------------------------------------------
# get_snippet: code-context extraction used to attach snippets to findings
# --------------------------------------------------------------------------

def test_snippet_marks_target_line(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("a = 1\nb = 2\nc = 3\nd = 4\ne = 5\n")
    snip = get_snippet(f, 3, context=1)
    assert ">>    3: c = 3" in snip
    assert "   2: b = 2" in snip
    assert "   4: d = 4" in snip
    # context=1 means line 1 and 5 are outside the window
    assert "a = 1" not in snip


def test_snippet_clamps_at_file_start(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("x = 1\ny = 2\n")
    snip = get_snippet(f, 1, context=2)
    assert ">>    1: x = 1" in snip  # no negative line numbers


def test_snippet_none_for_bad_inputs(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("x = 1\n")
    assert get_snippet(f, None) is None
    assert get_snippet(f, 0) is None
    assert get_snippet(tmp_path / "missing.py", 1) is None


# --------------------------------------------------------------------------
# TruffleHog mapper: JSONL secret findings -> unified issues
# --------------------------------------------------------------------------

def _th_line(detector="AWS", raw="AKIAEXAMPLE1234567890", line=7):
    return json.dumps({
        "DetectorName": detector,
        "Raw": raw,
        "SourceMetadata": {"Data": {"Filesystem": {"line": line}}},
    })


def test_trufflehog_maps_secret_to_issue():
    from qallm.analysis.trufflehog_analyzer import TruffleHogAnalyzer
    raw = RawToolResult("trufflehog", 0, _th_line(), "", "source.py")
    report = {"issues": []}
    TruffleHogAnalyzer().map_result_to_report(report, raw)
    assert len(report["issues"]) == 1
    issue = report["issues"][0]
    assert issue["test_id"] == "SECRET_EXPOSED"
    assert issue["tool"] == "trufflehog"
    assert issue["severity"] == "HIGH"
    assert issue["line_number"] == 7
    assert "AWS" in issue["issue_text"]


def test_trufflehog_multiple_jsonl_lines():
    from qallm.analysis.trufflehog_analyzer import TruffleHogAnalyzer
    stdout = "\n".join([_th_line("AWS", line=3), _th_line("GitHub", line=9)])
    raw = RawToolResult("trufflehog", 0, stdout, "", "source.py")
    report = {"issues": []}
    TruffleHogAnalyzer().map_result_to_report(report, raw)
    assert len(report["issues"]) == 2
    assert {i["line_number"] for i in report["issues"]} == {3, 9}


def test_trufflehog_blank_stdout_adds_nothing():
    from qallm.analysis.trufflehog_analyzer import TruffleHogAnalyzer
    report = {"issues": []}
    TruffleHogAnalyzer().map_result_to_report(
        report, RawToolResult("trufflehog", 0, "   ", "", "source.py"))
    assert report["issues"] == []


def test_trufflehog_skips_blank_lines_between_findings():
    from qallm.analysis.trufflehog_analyzer import TruffleHogAnalyzer
    stdout = _th_line("AWS", line=1) + "\n\n" + _th_line("GCP", line=2)
    raw = RawToolResult("trufflehog", 0, stdout, "", "source.py")
    report = {"issues": []}
    TruffleHogAnalyzer().map_result_to_report(report, raw)
    assert len(report["issues"]) == 2


def test_trufflehog_missing_line_metadata_defaults_to_zero():
    from qallm.analysis.trufflehog_analyzer import TruffleHogAnalyzer
    line = json.dumps({"DetectorName": "X", "Raw": "secret"})  # no metadata
    raw = RawToolResult("trufflehog", 0, line, "", "source.py")
    report = {"issues": []}
    TruffleHogAnalyzer().map_result_to_report(report, raw)
    assert report["issues"][0]["line_number"] == 0


# --------------------------------------------------------------------------
# Bandit JSON parsing robustness (security findings must survive noisy output)
# --------------------------------------------------------------------------

def test_bandit_parses_clean_json():
    from qallm.analysis.bandit_analyzer import BanditAnalyzer
    out = BanditAnalyzer()._safe_parse('{"results": []}')
    assert out == {"results": []}


def test_bandit_strips_ansi_then_parses():
    from qallm.analysis.bandit_analyzer import BanditAnalyzer
    noisy = '\x1b[31m{"results": [1]}\x1b[0m'
    assert BanditAnalyzer()._safe_parse(noisy) == {"results": [1]}


def test_bandit_recovers_json_from_surrounding_text():
    from qallm.analysis.bandit_analyzer import BanditAnalyzer
    # leading log noise before the JSON object
    noisy = 'WARNING: something\n{"results": [2]}\ntrailing'
    assert BanditAnalyzer()._safe_parse(noisy) == {"results": [2]}


def test_bandit_empty_and_unparseable_return_empty():
    from qallm.analysis.bandit_analyzer import BanditAnalyzer
    b = BanditAnalyzer()
    assert b._safe_parse("") == {}
    assert b._safe_parse("no json at all") == {}
