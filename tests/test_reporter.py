"""Tests for the rewritten qallm.utils.reporter.

Coverage:

  * Constructor creates the run directory.
  * save_baseline writes the round-0 static analysis only.
  * save_round_artefacts writes all six artefacts under lineage/round_N/<unit>/.
  * Rejected variants land under abandoned/round_N/<unit>/.
  * Tests directory contains one file per valid generated test.
  * Unit segments with path separators are escaped safely.
  * Sessions with no rounds skip test-file emission gracefully.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from qallm.analysis.analysis_model import AnalysedCodeUnit, Finding
from qallm.common.model import CodeUnit
from qallm.evaluation import (
    DimensionResult,
    IndicatorResult,
    IndicatorStatus,
    ProfileVerdict,
)
from qallm.profiles import QualityDimension
from qallm.utils.reporter import QualityReporter, _safe_unit_segment
from qallm.verification.models import (
    ExecutionResult,
    GeneratedTest,
    RewardBreakdown,
    RoundResult,
    TestedCodeUnit,
    TestGenerationSession,
)


# ---------- helpers ----------


def _reporter(tmp_path: Path, run_id: str = "test") -> QualityReporter:
    return QualityReporter(base_dir=str(tmp_path), run_id=run_id)


def _code_unit(tmp_path: Path, source: str = "def f(): pass\n", name: str = "x.py") -> CodeUnit:
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / name
    p.write_text(source)
    return CodeUnit(source_code=source, cell_index=-1, original_path=p)


def _analysed(unit: CodeUnit, findings: list[Finding] | None = None) -> AnalysedCodeUnit:
    return AnalysedCodeUnit(
        code_unit=unit,
        findings=findings or [],
        raw_tool_results=[],
    )


def _tested_with_one_session(
    unit: CodeUnit,
    function_name: str = "f",
    test_code: str = "def test_f(): assert True",
    valid: bool = True,
) -> TestedCodeUnit:
    """Construct a TestedCodeUnit with one session, one round."""
    from qallm.repair.repair_model import RepairedCodeUnit, RepairResult

    repaired_result = RepairResult(
        file_path=str(unit.original_path),
        repaired_source=unit.source_code,
        explanation="stub",
        compiles=True,
    )
    repaired = RepairedCodeUnit(
        analysis_result=AnalysedCodeUnit(code_unit=unit, findings=[], raw_tool_results=[]),
        repaired_result=repaired_result,
    )
    session = TestGenerationSession(
        function_name=function_name,
        source_code=unit.source_code,
        oracle="crash",
        model="stub",
        total_rounds=1,
    )
    session.rounds.append(RoundResult(
        round_number=1,
        generated_test=GeneratedTest(
            function_name=function_name,
            oracle="crash",
            test_code=test_code,
            is_valid=valid,
            generation_error=None,
            model="stub",
            provider="stub",
            input_tokens=0,
            output_tokens=0,
        ),
        execution=ExecutionResult(passed=1, failed=0, total=1, coverage_percent=100.0),
        reward=RewardBreakdown(total=1.0),
        cumulative_coverage=100.0,
        cumulative_bugs=0,
    ))
    return TestedCodeUnit(repaired_unit=repaired, sessions=[session])


def _profile_verdict() -> ProfileVerdict:
    return ProfileVerdict(
        profile_id="stub",
        dimensions=[
            DimensionResult(
                dimension=QualityDimension.MAINTAINABILITY,
                indicators=[
                    IndicatorResult(
                        name="mi", evaluator="stub", threshold=0.0,
                        comparator="ge", measured=70.0, status=IndicatorStatus.PASS,
                    )
                ],
            )
        ],
    )


# ---------- constructor ----------


def test_reporter_does_not_create_dir_on_construction(tmp_path: Path):
    # Regression: constructing a reporter must NOT create the session
    # directory. The orchestrator builds a reporter in its own constructor,
    # so eager creation left an empty directory on disk for every orchestrator
    # built but never run (e.g. ingest-only probes), producing bursts of empty
    # session folders. The directory must appear only on the first write.
    r = _reporter(tmp_path)
    assert not r.report_dir.exists()
    assert r.report_dir.name == "test"


def test_reporter_creates_run_directory_on_first_write(tmp_path: Path):
    r = _reporter(tmp_path)
    assert not r.report_dir.exists()
    r._ensure_dir()
    assert r.report_dir.exists()
    assert r.report_dir.is_dir()
    assert r.report_dir.name == "test"


# ---------- baseline ----------


class TestSaveBaseline:
    def test_writes_static_json_under_round_00_baseline(self, tmp_path: Path):
        r = _reporter(tmp_path)
        unit = _code_unit(tmp_path / "src", source="x = 1\n", name="mod.py")
        analysed = _analysed(unit)

        out_dir = r.save_baseline(analysed)
        assert out_dir == r.report_dir / "round_00_baseline"
        assert out_dir.exists()
        assert (out_dir / "mod_static.json").exists()

    def test_static_json_is_valid_json(self, tmp_path: Path):
        r = _reporter(tmp_path)
        unit = _code_unit(tmp_path / "src", name="mod.py")
        analysed = _analysed(unit)
        r.save_baseline(analysed)
        # Parses as JSON; findings is an empty list.
        text = (r.report_dir / "round_00_baseline" / "mod_static.json").read_text()
        assert json.loads(text) == []


# ---------- per-round artefacts ----------


class TestSaveRoundArtefactsAccepted:
    def test_routes_into_lineage_directory(self, tmp_path: Path):
        r = _reporter(tmp_path)
        unit = _code_unit(tmp_path / "src", name="mod.py")
        tested = _tested_with_one_session(unit)

        out = r.save_round_artefacts(
            round_number=1,
            unit_id="mod.py::-1",
            code_unit=unit,
            analysed=_analysed(unit),
            tested=tested,
            profile_verdict=_profile_verdict(),
            judge_verdict_dict=None,
            accepted=True,
        )

        assert "lineage" in str(out)
        assert "round_01" in str(out)

    def test_writes_all_six_artefacts(self, tmp_path: Path):
        r = _reporter(tmp_path)
        unit = _code_unit(tmp_path / "src", name="mod.py")
        tested = _tested_with_one_session(unit)
        out = r.save_round_artefacts(
            round_number=1,
            unit_id="mod.py::-1",
            code_unit=unit,
            analysed=_analysed(unit),
            tested=tested,
            profile_verdict=_profile_verdict(),
            judge_verdict_dict=None,
            accepted=True,
        )

        # Six artefacts per the v3 spec.
        assert (out / "source.py").exists()
        assert (out / "static.json").exists()
        assert (out / "verification.json").exists()
        assert (out / "profile.json").exists()
        assert (out / "judge.json").exists()
        assert (out / "tests").is_dir()
        # tests/ contains the generated test file
        assert (out / "tests" / "test_f.py").exists()

    def test_judge_json_is_null_when_no_judge_verdict(self, tmp_path: Path):
        r = _reporter(tmp_path)
        unit = _code_unit(tmp_path / "src", name="mod.py")
        tested = _tested_with_one_session(unit)
        out = r.save_round_artefacts(
            round_number=1,
            unit_id="mod.py::-1",
            code_unit=unit,
            analysed=_analysed(unit),
            tested=tested,
            profile_verdict=_profile_verdict(),
            judge_verdict_dict=None,
            accepted=True,
        )
        judge_text = (out / "judge.json").read_text()
        assert json.loads(judge_text) is None

    def test_judge_json_serialises_dict_when_present(self, tmp_path: Path):
        r = _reporter(tmp_path)
        unit = _code_unit(tmp_path / "src", name="mod.py")
        tested = _tested_with_one_session(unit)
        judge_dict = {"outcome": "improvement", "explanation": "mi rose"}
        out = r.save_round_artefacts(
            round_number=2,
            unit_id="mod.py::-1",
            code_unit=unit,
            analysed=_analysed(unit),
            tested=tested,
            profile_verdict=_profile_verdict(),
            judge_verdict_dict=judge_dict,
            accepted=True,
        )
        parsed = json.loads((out / "judge.json").read_text())
        assert parsed["outcome"] == "improvement"

    def test_source_py_contains_variant_source(self, tmp_path: Path):
        r = _reporter(tmp_path)
        unit = _code_unit(tmp_path / "src", source="def variant():\n    return 42\n")
        tested = _tested_with_one_session(unit)
        out = r.save_round_artefacts(
            round_number=1,
            unit_id="mod.py::-1",
            code_unit=unit,
            analysed=_analysed(unit),
            tested=tested,
            profile_verdict=_profile_verdict(),
            judge_verdict_dict=None,
            accepted=True,
        )
        assert "def variant" in (out / "source.py").read_text()


class TestSaveRoundArtefactsAbandoned:
    def test_routes_into_abandoned_directory(self, tmp_path: Path):
        r = _reporter(tmp_path)
        unit = _code_unit(tmp_path / "src", name="mod.py")
        tested = _tested_with_one_session(unit)
        out = r.save_round_artefacts(
            round_number=2,
            unit_id="mod.py::-1",
            code_unit=unit,
            analysed=_analysed(unit),
            tested=tested,
            profile_verdict=_profile_verdict(),
            judge_verdict_dict={"outcome": "regression", "explanation": "x"},
            accepted=False,
        )
        assert "abandoned" in str(out)
        assert "round_02" in str(out)

    def test_abandoned_has_same_artefacts_as_lineage(self, tmp_path: Path):
        r = _reporter(tmp_path)
        unit = _code_unit(tmp_path / "src", name="mod.py")
        tested = _tested_with_one_session(unit)
        out = r.save_round_artefacts(
            round_number=2,
            unit_id="mod.py::-1",
            code_unit=unit,
            analysed=_analysed(unit),
            tested=tested,
            profile_verdict=_profile_verdict(),
            judge_verdict_dict={"outcome": "regression"},
            accepted=False,
        )
        for name in ("source.py", "static.json", "verification.json",
                     "profile.json", "judge.json"):
            assert (out / name).exists()
        assert (out / "tests").is_dir()


class TestEdgeCases:
    def test_session_without_valid_test_skips_test_file(self, tmp_path: Path):
        r = _reporter(tmp_path)
        unit = _code_unit(tmp_path / "src")
        tested = _tested_with_one_session(unit, valid=False)
        out = r.save_round_artefacts(
            round_number=1,
            unit_id="mod.py::-1",
            code_unit=unit,
            analysed=_analysed(unit),
            tested=tested,
            profile_verdict=_profile_verdict(),
            judge_verdict_dict=None,
            accepted=True,
        )
        # Tests dir exists but is empty.
        assert (out / "tests").is_dir()
        assert list((out / "tests").iterdir()) == []

    def test_empty_sessions_list_writes_empty_verification(self, tmp_path: Path):
        from qallm.repair.repair_model import RepairedCodeUnit, RepairResult
        r = _reporter(tmp_path)
        unit = _code_unit(tmp_path / "src")
        repaired = RepairedCodeUnit(
            analysis_result=_analysed(unit),
            repaired_result=RepairResult(
                file_path=str(unit.original_path),
                repaired_source=unit.source_code,
                explanation="",
                compiles=True,
            ),
        )
        tested = TestedCodeUnit(repaired_unit=repaired, sessions=[])
        out = r.save_round_artefacts(
            round_number=1,
            unit_id="mod.py::-1",
            code_unit=unit,
            analysed=_analysed(unit),
            tested=tested,
            profile_verdict=_profile_verdict(),
            judge_verdict_dict=None,
            accepted=True,
        )
        parsed = json.loads((out / "verification.json").read_text())
        assert parsed == []


class TestUnitSegmentCleanNames:
    """The segment is filename + cell_index, NOT the full escaped path."""

    def test_basename_only_for_unix_path(self):
        # Long unix path collapses to just the basename.
        assert _safe_unit_segment("/var/folders/x/y/z/demo.py::0") == "demo.py__0"

    def test_basename_only_for_windows_path(self):
        # Same for Windows-style paths.
        assert _safe_unit_segment(r"C:\Users\foo\bar.ipynb::2") == "bar.ipynb__2"

    def test_simple_filename_unchanged(self):
        assert _safe_unit_segment("demo.py::3") == "demo.py__3"

    def test_negative_cell_index(self):
        # Cell index of -1 (used for whole-file ingestion) is preserved.
        assert _safe_unit_segment("demo.py::-1") == "demo.py__-1"

    def test_no_double_colon_falls_back_to_zero(self):
        # If somehow we get a unit_id without "::", treat the whole thing
        # as the path and default the cell index to 0.
        assert _safe_unit_segment("standalone.py") == "standalone.py__0"

    def test_empty_basename_after_trailing_slash(self):
        # Defensive: a trailing slash before "::" yields no basename.
        # We return "unit" as a fallback rather than an empty segment.
        assert _safe_unit_segment("foo/bar/::0") == "unit__0"

    def test_safe_segment_used_in_round_directory(self, tmp_path: Path):
        r = _reporter(tmp_path)
        unit = _code_unit(tmp_path / "src", name="mod.py")
        tested = _tested_with_one_session(unit)
        out = r.save_round_artefacts(
            round_number=1,
            unit_id="src/mod.py::-1",
            code_unit=unit,
            analysed=_analysed(unit),
            tested=tested,
            profile_verdict=_profile_verdict(),
            judge_verdict_dict=None,
            accepted=True,
        )
        # Directory name is just basename + cell index.
        assert out.name == "mod.py__-1"

    def test_temp_dir_path_does_not_explode(self, tmp_path: Path):
        # Regression: a unit_id derived from a system temp dir used to
        # produce a 100+ char folder name. Now: just the basename.
        r = _reporter(tmp_path)
        unit = _code_unit(tmp_path / "src", name="count_chars.py")
        tested = _tested_with_one_session(unit)
        long_id = "/var/folders/7z/yc4nm0ls6rg1gxbpqyg7frkmzzshkp/T/heval_Python_16_8o3xor8a/count_chars.py::0"
        out = r.save_round_artefacts(
            round_number=1,
            unit_id=long_id,
            code_unit=unit,
            analysed=_analysed(unit),
            tested=tested,
            profile_verdict=_profile_verdict(),
            judge_verdict_dict=None,
            accepted=True,
        )
        assert out.name == "count_chars.py__0"
        # And it's short.
        assert len(out.name) < 30
