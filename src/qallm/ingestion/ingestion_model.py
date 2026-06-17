import json
import re
from pathlib import Path
from typing import List

from qallm.common.model import CodeUnit


class NotebookAdapter:
    """Handles .ipynb files by stripping magics and preserving cell order."""
    MAGIC_PATTERN = re.compile(r"^(%|!|%%).*$", re.MULTILINE)

    def parse(self, path: Path) -> List[CodeUnit]:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        units = []
        # Scraped corpora contain malformed notebooks: cells that are strings
        # rather than dicts, a top-level value that is not an object, or a
        # source given as a single string instead of a list of lines. Guard
        # each of these so one odd notebook does not raise (this was the
        # 'str' object has no attribute 'get' failure that dropped ~10% of the
        # ENVRI corpus); skip what cannot be read and keep the valid cells.
        cells = data.get('cells', []) if isinstance(data, dict) else []
        for idx, cell in enumerate(cells):
            if not isinstance(cell, dict):
                continue
            if cell.get('cell_type') != 'code':
                continue
            source = cell.get('source', [])
            if isinstance(source, str):
                raw = source
            elif isinstance(source, list):
                raw = "".join(s for s in source if isinstance(s, str))
            else:
                continue
            cleaned = self.MAGIC_PATTERN.sub("", raw)
            units.append(CodeUnit(cleaned, idx, path))
        return units