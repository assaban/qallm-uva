import json
import re
from pathlib import Path
from typing import List


class CodeUnit:
    """Represents a single executable unit of code extracted from an artifact."""

    def __init__(self, source: str, cell_index: int, original_path: Path):
        self.source = source
        self.cell_index = cell_index
        self.original_path = original_path


class NotebookAdapter:
    """Stage 1: Preprocessing for .ipynb files[cite: 616]."""

    # Matches Jupyter magics (%line, %%cell) and shell commands (!pip)
    # This prevents execution crashes during Stage 3 [cite: 616]
    MAGIC_PATTERN = re.compile(r"^(%|!|%%).*$", re.MULTILINE)

    def parse(self, path: Path) -> List[CodeUnit]:
        """Parses ipynb structure and extracts code cells[cite: 616]."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        code_units = []
        for idx, cell in enumerate(data.get('cells', [])):
            if cell.get('cell_type') == 'code':
                raw_source = "".join(cell.get('source', []))
                # Strip magics while preserving cell order [cite: 616]
                cleaned_source = self.MAGIC_PATTERN.sub("", raw_source)

                code_units.append(CodeUnit(
                    source=cleaned_source,
                    cell_index=idx,
                    original_path=path
                ))
        return code_units