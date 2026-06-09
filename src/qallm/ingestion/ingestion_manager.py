import os
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import List
import git  # Requires pip install gitpython

from qallm.common.model import CodeUnit
from qallm.ingestion.ingestion_model import NotebookAdapter
from qallm.ingestion.triviality import assess_triviality

logger = logging.getLogger(__name__)


class IngestionManager:
    """Stage 1: Preprocessing manager for multi-source research artifacts."""

    def __init__(self):
        self.nb_adapter = NotebookAdapter()
        # Units skipped as non-analyzable, recorded for auditability and
        # reporting (e.g. "N files skipped, nothing to verify").
        self.skipped: list[dict] = []

    def collect(self, source: str) -> List[CodeUnit]:
        """Collect analyzable units from files, directories, ZIPs, or git URLs.

        Units with nothing to analyze (empty or import-only files, the bare
        __init__.py case) are filtered out so they do not consume analysis,
        test-generation, and LLM-repair resources or skew the metrics.
        """
        return self._filter_trivial(self._collect_raw(source))

    def _collect_raw(self, source: str) -> List[CodeUnit]:
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

    def _filter_trivial(self, units: List[CodeUnit]) -> List[CodeUnit]:
        kept: List[CodeUnit] = []
        for unit in units:
            verdict = assess_triviality(unit.source_code)
            if verdict.is_trivial:
                self.skipped.append({
                    "path": str(unit.original_path),
                    "cell_index": unit.cell_index,
                    "reason": verdict.reason,
                })
                logger.info("Skipping non-analyzable unit %s (cell %s): %s",
                            unit.original_path, unit.cell_index, verdict.reason)
            else:
                kept.append(unit)
        if self.skipped:
            logger.info("Ingestion skipped %d non-analyzable unit(s); kept %d.",
                        len(self.skipped), len(kept))
        return kept

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
        for root, dirs, files in os.walk(directory):
            # Skip Jupyter autosave backups: .ipynb_checkpoints holds
            # "-checkpoint.ipynb" duplicates of real notebooks. Including them
            # double-processes the same code, wastes budget, and pollutes the
            # results (the ENVRI run was spending rounds on checkpoint copies).
            # Pruning dirs in-place stops os.walk descending into them.
            dirs[:] = [d for d in dirs if d != ".ipynb_checkpoints"]
            for file in files:
                fpath = Path(root) / file
                if fpath.suffix == '.ipynb':
                    units.extend(self.nb_adapter.parse(fpath))
                elif fpath.suffix == '.py':
                    with open(fpath, 'r') as f:
                        units.append(CodeUnit(f.read(), 0, fpath))
        return units