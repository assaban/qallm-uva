"""Round-to-round diffs of the repaired code and the generated tests.

A reviewer comparing round N to round N-1 wants to see exactly what changed:
the repaired source, and the generated tests. This module reads the persisted
``source.py`` and ``tests/`` artefacts for two rounds of one code unit and
returns both the raw texts (for a side-by-side / raw view) and unified diffs
(for a GitHub-style review), so the UI can offer either.

Read-only. It reads the artefacts the reporter already writes per round and
computes diffs with difflib; it does not affect the pipeline.
"""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass, field
from typing import Optional


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _round_no(name: str) -> Optional[int]:
    try:
        return int(name.replace("round_", ""))
    except ValueError:
        return None


def _unified(old: str, new: str, label: str) -> str:
    """A unified diff between two texts, empty string when identical."""
    if old == new:
        return ""
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{label}",
        tofile=f"b/{label}",
        n=3,
    )
    return "".join(diff)


@dataclass
class FileDiff:
    """One diffed artefact: its raw before/after and the unified diff."""

    label: str           # e.g. "source.py" or "test_inclusive_range_count.py"
    kind: str            # "code" or "test"
    old_text: str
    new_text: str
    unified: str
    changed: bool

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "kind": self.kind,
            "old_text": self.old_text,
            "new_text": self.new_text,
            "unified": self.unified,
            "changed": self.changed,
        }


@dataclass
class RoundDiff:
    """All artefact diffs between two rounds of one code unit."""

    unit: str
    from_round: Optional[int]
    to_round: int
    files: list[FileDiff] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "unit": self.unit,
            "from_round": self.from_round,
            "to_round": self.to_round,
            "files": [f.to_dict() for f in self.files],
        }


def _round_dir(report_dir: str, bucket: str, round_no: int) -> Optional[str]:
    path = os.path.join(report_dir, bucket, f"round_{round_no:02d}")
    return path if os.path.isdir(path) else None


def _find_round_dir(report_dir: str, round_no: int) -> Optional[str]:
    """A round can live under lineage/ (accepted) or abandoned/ (rejected)."""
    for bucket in ("lineage", "abandoned"):
        d = _round_dir(report_dir, bucket, round_no)
        if d:
            return d
    return None


def _unit_dir(round_dir: str, unit: Optional[str]) -> Optional[str]:
    if not os.path.isdir(round_dir):
        return None
    units = sorted(
        seg for seg in os.listdir(round_dir)
        if os.path.isdir(os.path.join(round_dir, seg))
    )
    if not units:
        return None
    if unit and unit in units:
        return os.path.join(round_dir, unit)
    # Default to the first unit; most sessions have exactly one.
    return os.path.join(round_dir, units[0])


def _test_files(unit_dir: str) -> dict[str, str]:
    """Map test filename -> contents for a unit's tests/ directory."""
    tests_dir = os.path.join(unit_dir, "tests")
    out: dict[str, str] = {}
    if not os.path.isdir(tests_dir):
        return out
    for fname in sorted(os.listdir(tests_dir)):
        if fname.startswith("test_") and fname.endswith(".py"):
            out[fname] = _read_text(os.path.join(tests_dir, fname))
    return out


def available_rounds(report_dir: str) -> list[int]:
    """Round numbers present in the session, sorted."""
    rounds: set[int] = set()
    for bucket in ("lineage", "abandoned"):
        bucket_dir = os.path.join(report_dir, bucket)
        if not os.path.isdir(bucket_dir):
            continue
        for name in os.listdir(bucket_dir):
            n = _round_no(name)
            if n is not None:
                rounds.add(n)
    return sorted(rounds)


def diff_rounds(
    report_dir: str,
    to_round: int,
    from_round: Optional[int] = None,
    unit: Optional[str] = None,
) -> RoundDiff:
    """Diff the repaired code and generated tests of two rounds.

    ``to_round`` is the later round; ``from_round`` defaults to ``to_round - 1``
    (the immediate parent). When ``from_round`` is None and ``to_round`` is 0,
    the diff is against an empty baseline (everything is new).
    """
    if from_round is None:
        from_round = to_round - 1 if to_round > 0 else None

    to_dir = _find_round_dir(report_dir, to_round)
    to_unit = _unit_dir(to_dir, unit) if to_dir else None
    from_dir = _find_round_dir(report_dir, from_round) if from_round is not None else None
    from_unit = _unit_dir(from_dir, unit) if from_dir else None

    result = RoundDiff(unit=unit or "", from_round=from_round, to_round=to_round)
    if not to_unit:
        return result
    result.unit = os.path.basename(to_unit)

    # 1. the repaired code (source.py)
    new_src = _read_text(os.path.join(to_unit, "source.py"))
    old_src = _read_text(os.path.join(from_unit, "source.py")) if from_unit else ""
    result.files.append(FileDiff(
        label="source.py", kind="code",
        old_text=old_src, new_text=new_src,
        unified=_unified(old_src, new_src, "source.py"),
        changed=old_src != new_src,
    ))

    # 2. the generated tests, one FileDiff per test file (union of both rounds)
    new_tests = _test_files(to_unit)
    old_tests = _test_files(from_unit) if from_unit else {}
    for fname in sorted(set(new_tests) | set(old_tests)):
        o, n = old_tests.get(fname, ""), new_tests.get(fname, "")
        result.files.append(FileDiff(
            label=fname, kind="test",
            old_text=o, new_text=n,
            unified=_unified(o, n, fname),
            changed=o != n,
        ))
    return result
