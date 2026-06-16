"""Tests for attaching mutation-based confidence to gap findings."""

from pathlib import Path
from qallm.experiments.gap_confidence import score_gap_confidence_from_dir


def _make_report(tmp_path: Path, source: str, tests: dict[str, str],
                 round_name: str = "round_00") -> Path:
    unit = tmp_path / "lineage" / round_name / "unit.py__0"
    (unit / "tests").mkdir(parents=True)
    (unit / "source.py").write_text(source)
    for fn, code in tests.items():
        (unit / "tests" / f"test_{fn}.py").write_text(code)
    return tmp_path


SRC = "def inc(start, end):\n    return end - start + 1\n"
STRONG = ("from source_module import inc\n"
          "def test_a():\n    assert inc(0, 10) == 11\n"
          "def test_b():\n    assert inc(5, 5) == 1\n")
WEAK = ("from source_module import inc\n"
        "def test_a():\n    assert isinstance(inc(0, 10), int)\n")


def test_strong_gap_function_scores_high(tmp_path):
    rd = _make_report(tmp_path, SRC, {"inc": STRONG})
    res = score_gap_confidence_from_dir(str(rd), ["inc"])
    assert res["scored"] == 1
    assert res["per_function"]["inc"]["confidence"] == "high"
    assert res["distribution"]["high"] == 1


def test_weak_gap_function_scores_low(tmp_path):
    rd = _make_report(tmp_path, SRC, {"inc": WEAK})
    res = score_gap_confidence_from_dir(str(rd), ["inc"])
    assert res["per_function"]["inc"]["confidence"] in ("low", "medium")


def test_restricts_to_requested_functions(tmp_path):
    rd = _make_report(tmp_path, SRC, {"inc": STRONG})
    # ask for a function that has no suite -> nothing scored
    res = score_gap_confidence_from_dir(str(rd), ["other"])
    assert res["scored"] == 0


def test_tolerates_round_0_naming(tmp_path):
    rd = _make_report(tmp_path, SRC, {"inc": STRONG}, round_name="round_0")
    res = score_gap_confidence_from_dir(str(rd), ["inc"])
    assert res["scored"] == 1


def test_missing_report_dir_is_safe(tmp_path):
    res = score_gap_confidence_from_dir(str(tmp_path / "nope"), ["inc"])
    assert res["scored"] == 0
    assert res["per_function"] == {}


def test_aggregate_folds_confidence_distribution(tmp_path, monkeypatch):
    """The run aggregate combines per-session gap-confidence distributions and
    exposes a high-confidence gap count."""
    import json
    from qallm.experiments import gap_runner

    ds = tmp_path / "ds"
    ds.mkdir()
    (ds / "a.py").write_text("def g(): return 1\n")
    (ds / "b.py").write_text("def h(): return 2\n")
    out = tmp_path / "out"

    # Stub _run_one to return rows carrying gap_confidence blocks, so we test
    # the aggregate folding without invoking the pipeline.
    calls = {"n": 0}
    def fake_run_one(input_path, config, factory):
        calls["n"] += 1
        dist = ({"high": 2, "medium": 0, "low": 0, "unknown": 0}
                if calls["n"] == 1 else
                {"high": 1, "medium": 0, "low": 1, "unknown": 0})
        return {
            "input": str(input_path),
            "metrics": {"session_id": f"s{calls['n']}", "model": "m",
                        "oracle": "correctness"},
            "error": None,
            "gap_confidence": {"distribution": dist,
                               "scored": sum(dist.values())},
        }
    monkeypatch.setattr(gap_runner, "_run_one", fake_run_one)

    cfg = gap_runner.GapExperimentConfig(
        dataset_dir=ds, output_dir=out, pattern="*.py", rounds=1,
        mutation_confidence=True,
    )
    gap_runner.run_gap_experiment(cfg, orchestrator_factory=lambda c: None)

    agg = json.loads((out / "aggregate.json").read_text())
    assert "gap_confidence" in agg
    assert agg["gap_confidence"]["distribution"] == {
        "high": 3, "medium": 0, "low": 1, "unknown": 0}
    assert agg["gap_confidence"]["high_confidence_gap_bugs"] == 3


def test_only_scores_functions_present_in_unit_source(tmp_path):
    """A gap function whose test file sits in a unit but is NOT defined in that
    unit's source must not be scored as 'unknown' (it lives elsewhere)."""
    rd = tmp_path / "rep"
    unit = rd / "lineage" / "round_00" / "u1"
    (unit / "tests").mkdir(parents=True)
    (unit / "source.py").write_text("def present(x):\n    return x + 1\n")
    # a stray test file for a function not in this source
    (unit / "tests" / "test_absent.py").write_text(
        "from source_module import absent\ndef t(): assert absent(1) == 1\n")
    (unit / "tests" / "test_present.py").write_text(
        "from source_module import present\n"
        "def t(): assert present(0) == 1\n")
    res = score_gap_confidence_from_dir(str(rd), ["present", "absent"])
    assert "present" in res["per_function"]
    assert "absent" not in res["per_function"]
    assert res.get("unresolved") == ["absent"]


def test_function_scored_once_across_units(tmp_path):
    rd = tmp_path / "rep"
    for i in (1, 2):
        unit = rd / "lineage" / "round_00" / f"u{i}"
        (unit / "tests").mkdir(parents=True)
        (unit / "source.py").write_text("def f(x):\n    return x + 1\n")
        (unit / "tests" / "test_f.py").write_text(
            "from source_module import f\ndef t(): assert f(0) == 1\n")
    res = score_gap_confidence_from_dir(str(rd), ["f"])
    assert res["scored"] == 1


def test_gap_function_scored_against_repaired_not_buggy_original(tmp_path):
    """A gap function's round-0 source is buggy (the suite fails on it), so
    mutation scoring must use the repaired source where the suite passes, else
    every mutant is not-viable and the function wrongly scores 'unknown'."""
    rd = tmp_path / "report"
    u0 = rd / "lineage" / "round_00" / "u0"
    (u0 / "tests").mkdir(parents=True)
    # buggy original: off-by-one
    (u0 / "source.py").write_text(
        "def inc(start, end):\n    return end - start\n")
    (u0 / "tests" / "test_inc.py").write_text(
        "from source_module import inc\n"
        "def test_a(): assert inc(1, 5) == 5\n"
        "def test_b(): assert inc(0, 0) == 1\n")
    # repaired version in a later round
    u1 = rd / "lineage" / "round_01" / "u0"
    u1.mkdir(parents=True)
    (u1 / "source.py").write_text(
        "def inc(start, end):\n    return end - start + 1\n")
    res = score_gap_confidence_from_dir(str(rd), ["inc"])
    pf = res["per_function"]["inc"]
    assert pf["confidence"] in ("high", "medium", "low")  # not unknown
    assert pf["viable"] > 0
