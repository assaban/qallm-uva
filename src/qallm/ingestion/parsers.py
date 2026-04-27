import json
import re
import os
import tempfile
import zipfile
from pathlib import Path
from typing import List
import git  # Requires pip install gitpython


class CodeUnit:
    """Represents a single executable unit of code[cite: 76]."""

    def __init__(self, source: str, cell_index: int, original_path: Path):
        self.source = source
        self.cell_index = cell_index
        self.original_path = original_path


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


class IngestionManager:
    """Stage 1: Preprocessing manager for multi-source research artifacts."""

    def __init__(self):
        self.nb_adapter = NotebookAdapter()

    def collect(self, source: str) -> List[CodeUnit]:
        """Collects units from single files, directories, ZIPs, or GitHub URLs."""
        if source.startswith(("http://", "https://")):
            return self._handle_git(source)

        path = Path(source)
        if path.suffix == '.zip':
            return self._handle_zip(path)
        if path.is_dir():
            return self._scan_directory(path)
        if path.suffix == '.ipynb':
            return self.nb_adapter.parse(path)
        if path.suffix == '.py':
            with open(path, 'r') as f:
                return [CodeUnit(f.read(), 0, path)]
        return []

    def _handle_git(self, url: str) -> List[CodeUnit]:
        tmp_dir = tempfile.mkdtemp()
        git.Repo.clone_from(url, tmp_dir)
        return self._scan_directory(Path(tmp_dir))

    def _handle_zip(self, path: Path) -> List[CodeUnit]:
        tmp_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(path, 'r') as z:
            z.extractall(tmp_dir)
        return self._scan_directory(Path(tmp_dir))

    def _scan_directory(self, directory: Path) -> List[CodeUnit]:
        units = []
        for root, _, files in os.walk(directory):
            for file in files:
                fpath = Path(root) / file
                if fpath.suffix == '.ipynb':
                    units.extend(self.nb_adapter.parse(fpath))
                elif fpath.suffix == '.py':
                    with open(fpath, 'r') as f:
                        units.append(CodeUnit(f.read(), 0, fpath))
        return units