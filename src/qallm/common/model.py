from pathlib import Path


class CodeUnit:
    """Represents a single executable unit of code."""

    def __init__(self, source_code: str, cell_index: int, original_path: Path):
        self.source_code = source_code
        self.cell_index = cell_index
        self.original_path = original_path
