"""IngestionManager filters non-analyzable units and records what it skipped."""

import os
import tempfile
from pathlib import Path

from qallm.ingestion.ingestion_manager import IngestionManager


def _write(d, name, content):
    p = Path(d) / name
    p.write_text(content)
    return p


def test_directory_scan_skips_empty_and_import_only():
    with tempfile.TemporaryDirectory() as d:
        _write(d, "__init__.py", "")                       # empty -> skip
        _write(d, "exports.py", "from .core import A\n")   # import-only -> skip
        _write(d, "core.py", "def a():\n    return 1\n")   # real -> keep
        mgr = IngestionManager()
        units = mgr.collect(d)
        kept_paths = {Path(u.original_path).name for u in units}
        assert kept_paths == {"core.py"}
        assert len(mgr.skipped) == 2
        reasons = {s["path"].split("/")[-1]: s["reason"] for s in mgr.skipped}
        assert "__init__.py" in reasons and "exports.py" in reasons


def test_single_empty_file_yields_no_units():
    with tempfile.TemporaryDirectory() as d:
        p = _write(d, "empty.py", "# just a header comment\n")
        mgr = IngestionManager()
        units = mgr.collect(str(p))
        assert units == []
        assert len(mgr.skipped) == 1


def test_real_file_is_kept():
    with tempfile.TemporaryDirectory() as d:
        p = _write(d, "logic.py", "def f(x):\n    return x * 2\n")
        mgr = IngestionManager()
        units = mgr.collect(str(p))
        assert len(units) == 1
        assert mgr.skipped == []


def test_syntax_error_file_is_not_skipped():
    with tempfile.TemporaryDirectory() as d:
        p = _write(d, "broken.py", "def f(:\n    pass\n")
        mgr = IngestionManager()
        units = mgr.collect(str(p))
        assert len(units) == 1          # kept: a syntax error is a real signal
        assert mgr.skipped == []
