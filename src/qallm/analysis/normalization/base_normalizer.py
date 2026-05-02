from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from qallm.analysis.models import Finding, RawToolResult


@dataclass
class NormalizationContext:
    session_id: str
    workspace_dir: Path
    reports_dir: Path


class ToolNormalizer(ABC):
    tool_name: str

    @abstractmethod
    def normalize(self, result: RawToolResult) -> list[Finding]: ...
