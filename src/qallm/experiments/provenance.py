"""Capture provenance for an experiment run.

Every reported number should trace back to the exact conditions that produced
it: which code, which model, which inputs, when. This module gathers that
provenance so it can be written into the run manifest. The thesis protocol asks
for this; capturing it automatically means no number is ever orphaned from its
conditions, which is the reproducibility spine an examiner expects.

Everything here is best-effort: provenance must never crash a run. A field that
cannot be determined (no git repo, version metadata missing) is recorded as
None or "unknown" rather than raising.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _git(*args: str) -> str | None:
    """Run a git command in the package's repo, returning stripped stdout or
    None if git is unavailable or the command fails."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        out = subprocess.run(
            ["git", *args],
            cwd=here, capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _git_info() -> dict:
    """Commit hash, branch, and whether the working tree was dirty.

    A dirty tree means tracked files were modified relative to the recorded
    commit, so the run did not correspond exactly to that commit: a
    reproducibility caveat worth recording, not hiding. Untracked files (data
    sets, run outputs, zipped artefacts copied between machines) do not change
    what code executed, so they are deliberately excluded from the dirty flag;
    counting them made clean runs report as dirty. Their presence is still
    recorded separately as ``untracked`` for transparency.
    """
    commit = _git("rev-parse", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    # --untracked-files=no: only tracked-file modifications count as dirty.
    tracked_status = _git("status", "--porcelain", "--untracked-files=no")
    full_status = _git("status", "--porcelain")
    untracked = 0
    if full_status:
        untracked = sum(1 for ln in full_status.splitlines() if ln.startswith("??"))
    return {
        "commit": commit,
        "branch": branch,
        "dirty": bool(tracked_status) if tracked_status is not None else None,
        "untracked": untracked,
    }


def _package_version() -> str | None:
    try:
        from importlib.metadata import version
        return version("qallm")
    except Exception:
        return None


def dataset_fingerprint(inputs: list) -> dict:
    """A content-independent fingerprint of the input set.

    Records the file count and a hash over the sorted relative paths, so two
    runs over "the same dataset" can be shown to have used the same files (or
    not). Hashing paths, not contents, keeps it cheap; contents are captured
    per unit in the artefacts already.
    """
    paths = sorted(str(p) for p in inputs)
    h = hashlib.sha256("\n".join(paths).encode("utf-8")).hexdigest()
    return {"n_inputs": len(paths), "paths_sha256": h}


def capture(extra: dict | None = None) -> dict:
    """Assemble the provenance block.

    Args:
        extra: additional run-specific fields to merge (e.g. dataset
            fingerprint), kept here so the caller can add what only it knows.
    """
    prov = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "qallm_version": _package_version(),
        "git": _git_info(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "executable": sys.executable,
    }
    if extra:
        prov.update(extra)
    return prov
