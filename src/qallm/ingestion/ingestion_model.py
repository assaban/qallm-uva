import json
import re
from pathlib import Path
from typing import List

from qallm.common.model import CodeUnit


class NotebookAdapter:
    """Handles .ipynb files by stripping magics and preserving cell order[cite: 76]."""
    MAGIC_PATTERN = re.compile(r"^(%|!|%%).*$", re.MULTILINE)

    def parse(self, path: Path) -> List[CodeUnit]:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        units = []
        for idx, cell in enumerate(data.get('cells', [])):
            if cell.get('cell_type') == 'code':
                raw = "".join(cell.get('source', []))
                cleaned = self.MAGIC_PATTERN.sub("", raw)
                units.append(CodeUnit(cleaned, idx, path))
        return units