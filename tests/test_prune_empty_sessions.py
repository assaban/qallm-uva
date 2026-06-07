"""Tests for pruning empty session directories."""

import os
from pathlib import Path

from qallm.api.routers.sessions_library import prune_empty_sessions


def test_removes_empty_dirs_only(tmp_path: Path):
    base = tmp_path / "quality_reporter"
    base.mkdir()
    # Two empty session dirs (the bug's residue).
    (base / "empty_1").mkdir()
    (base / "empty_2").mkdir()
    # One empty dir with an empty subdir (still no files) -> should be removed.
    (base / "empty_nested" / "lineage").mkdir(parents=True)
    # A real session with artefacts -> must be kept.
    real = base / "real_session" / "lineage" / "round_00" / "unit"
    real.mkdir(parents=True)
    (real / "source.py").write_text("def f(): return 1\n")
    (base / "real_session" / "summary.json").write_text("{}")

    removed = prune_empty_sessions(str(base))

    assert set(removed) == {"empty_1", "empty_2", "empty_nested"}
    assert not (base / "empty_1").exists()
    assert not (base / "empty_nested").exists()
    # The real session is untouched.
    assert (base / "real_session" / "summary.json").exists()
    assert (real / "source.py").exists()


def test_never_removes_dir_with_any_file(tmp_path: Path):
    base = tmp_path / "q"
    base.mkdir()
    # A dir whose only content is a single deeply-nested file must survive.
    d = base / "has_one_file" / "a" / "b" / "c"
    d.mkdir(parents=True)
    (d / "lonely.json").write_text("{}")
    removed = prune_empty_sessions(str(base))
    assert removed == []
    assert (d / "lonely.json").exists()


def test_missing_base_dir_is_safe(tmp_path: Path):
    assert prune_empty_sessions(str(tmp_path / "does_not_exist")) == []


def test_ignores_loose_files_at_base(tmp_path: Path):
    base = tmp_path / "q"
    base.mkdir()
    (base / "a_loose_file.zip").write_text("x")   # not a dir; ignored
    (base / "empty").mkdir()
    removed = prune_empty_sessions(str(base))
    assert removed == ["empty"]
    assert (base / "a_loose_file.zip").exists()
