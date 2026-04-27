import pytest
from pathlib import Path
from qallm.ingestion.parsers import NotebookAdapter


@pytest.fixture
def sample_notebook(tmp_path):
    """Creates a temporary Jupyter Notebook file for testing."""
    import json
    nb_content = {
        "cells": [
            {
                "cell_type": "code",
                "source": ["%matplotlib inline\n", "import pandas as pd\n", "print('hello')"]
            },
            {
                "cell_type": "markdown",
                "source": ["# This should be ignored"]
            },
            {
                "cell_type": "code",
                "source": ["!pip install numpy\n", "import numpy as np"]
            }
        ]
    }
    nb_path = tmp_path / "test_notebook.ipynb"
    with open(nb_path, "w") as f:
        json.dump(nb_content, f)
    return nb_path


def test_notebook_adapter_extraction(sample_notebook):
    """Validates Stage 1: Extraction of code cells only[cite: 616]."""
    adapter = NotebookAdapter()
    units = adapter.parse(sample_notebook)

    # We expect 2 units because the markdown cell is ignored [cite: 616]
    assert len(units) == 2
    assert units[0].cell_index == 0
    assert units[1].cell_index == 2


def test_notebook_adapter_magic_stripping(sample_notebook):
    """Validates that Jupyter magics and shell commands are removed[cite: 616, 808]."""
    adapter = NotebookAdapter()
    units = adapter.parse(sample_notebook)

    # Check first unit (removed %matplotlib)
    assert "%matplotlib" not in units[0].source
    assert "import pandas as pd" in units[0].source

    # Check second unit (removed !pip)
    assert "!pip" not in units[1].source
    assert "import numpy as np" in units[1].source


def test_empty_notebook(tmp_path):
    """Ensures robustness against empty files (NFR6)[cite: 165]."""
    nb_path = tmp_path / "empty.ipynb"
    with open(nb_path, "w") as f:
        import json
        json.dump({"cells": []}, f)

    adapter = NotebookAdapter()
    units = adapter.parse(nb_path)
    assert len(units) == 0