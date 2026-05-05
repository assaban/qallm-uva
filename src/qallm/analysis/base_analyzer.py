from __future__ import annotations

from abc import ABC, abstractmethod

from qallm.analysis.analysis_model import RawToolResult
from qallm.analysis.normalization.base_normalizer import ToolNormalizer
from qallm.common.model import CodeUnit


class StaticCodeAnalyzer(ABC):
    """Abstract Strategy for all static analysis tools."""

    @abstractmethod
    def tool_name(self) -> str:
        """Returns the unique identifier for the tool."""
        ...

    @abstractmethod
    def analyze(self, unit: CodeUnit) -> RawToolResult:
        """Executes the tool for a specific code unit."""
        ...

    @abstractmethod
    def get_normalizer(self) -> ToolNormalizer:
        """Returns the tool report normalizer for a specific code unit."""
        ...
