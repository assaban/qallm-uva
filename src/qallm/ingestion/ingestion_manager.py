import os
import tempfile
import zipfile
from pathlib import Path
from typing import List
import git  # Requires pip install gitpython

from qallm.common.model import CodeUnit
from qallm.ingestion.ingestion_model import NotebookAdapter


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