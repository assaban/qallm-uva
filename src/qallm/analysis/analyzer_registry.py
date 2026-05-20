from __future__ import annotations
from typing import Iterable, List
from .base_analyzer import StaticCodeAnalyzer


class AnalyzerRegistry:
    """Registry for managing and selecting analysis strategies."""

    def __init__(self, analyzers: Iterable[StaticCodeAnalyzer]):
        self._by_name = {a.tool_name(): a for a in analyzers}

    def list(self) -> List[str]:
        """Returns list of registered tool names."""
        return sorted(self._by_name.keys())

    def get(self, name: str) -> StaticCodeAnalyzer:
        """Retrieves a specific analyzer by name."""
        return self._by_name[name]

    def pick(self, selected: List[str] | None) -> List[StaticCodeAnalyzer]:
        """Filters available tools based on user selection or returns all."""
        if not selected:
            return [self._by_name[k] for k in self.list()]
        return [self._by_name[n] for n in selected if n in self._by_name]