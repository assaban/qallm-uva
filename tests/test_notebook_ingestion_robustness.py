"""Malformed notebooks must not crash ingestion (scraped corpora are messy)."""

import json

from qallm.ingestion.ingestion_model import NotebookAdapter


def _write(tmp_path, nb):
    p = tmp_path / "nb.ipynb"
    p.write_text(json.dumps(nb))
    return p


def test_string_cell_is_skipped_not_crashed(tmp_path):
    # A cell that is a bare string (not a dict) used to raise
    # 'str' object has no attribute 'get' and drop the whole notebook.
    nb = {"cells": ["oops a string", {"cell_type": "code", "source": ["x = 1\n"]}]}
    units = NotebookAdapter().parse(_write(tmp_path, nb))
    assert len(units) == 1
    assert "x = 1" in units[0].source_code


def test_source_as_string_is_handled(tmp_path):
    nb = {"cells": [{"cell_type": "code", "source": "y = 2\n"}]}
    units = NotebookAdapter().parse(_write(tmp_path, nb))
    assert len(units) == 1
    assert "y = 2" in units[0].source_code


def test_non_dict_top_level_yields_no_units(tmp_path):
    units = NotebookAdapter().parse(_write(tmp_path, ["not", "a", "notebook"]))
    assert units == []


def test_normal_notebook_still_works(tmp_path):
    nb = {"cells": [{"cell_type": "code", "source": ["def f():\n", "    return 1\n"]},
                    {"cell_type": "markdown", "source": ["# title\n"]}]}
    units = NotebookAdapter().parse(_write(tmp_path, nb))
    assert len(units) == 1  # markdown skipped
    assert "def f" in units[0].source_code
