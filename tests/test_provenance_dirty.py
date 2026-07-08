"""Dirty detection must ignore untracked files.

The manifest previously ran `git status --porcelain`, which lists untracked
files too, so a clean checkout with data sets, run outputs, or zipped artefacts
sitting in the tree was reported as dirty. Only modifications to tracked files
mean the run did not match the recorded commit. These tests pin that untracked
files do not set the dirty flag, and that a tracked-file change does.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from qallm.experiments import provenance


def _run(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _run(tmp_path, "init")
    _run(tmp_path, "config", "user.email", "x@x")
    _run(tmp_path, "config", "user.name", "x")
    (tmp_path / "code.py").write_text("code\n")
    _run(tmp_path, "add", "code.py")
    _run(tmp_path, "commit", "-m", "init")

    # Point the provenance git helper at this throwaway repo.
    def _git(*args: str):
        out = subprocess.run(["git", *args], cwd=tmp_path,
                             capture_output=True, text=True)
        return out.stdout.strip() if out.returncode == 0 else None

    monkeypatch.setattr(provenance, "_git", _git)
    return tmp_path


def test_clean_tree_not_dirty(repo: Path) -> None:
    info = provenance._git_info()
    assert info["dirty"] is False
    assert info["untracked"] == 0


def test_untracked_file_not_dirty(repo: Path) -> None:
    (repo / "data.zip").write_text("junk")
    (repo / "runs").mkdir()
    (repo / "runs" / "out.json").write_text("{}")
    info = provenance._git_info()
    assert info["dirty"] is False          # untracked artefacts do not count
    assert info["untracked"] >= 1          # but are recorded


def test_tracked_change_is_dirty(repo: Path) -> None:
    (repo / "code.py").write_text("code\n# modified\n")
    assert provenance._git_info()["dirty"] is True
