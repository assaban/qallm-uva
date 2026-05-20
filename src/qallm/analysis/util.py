from pathlib import Path


def get_snippet(rel_file: Path, line: int | None, context: int = 2) -> str | None:
    if not rel_file or not line or line < 1:
        return None

    fp = rel_file
    if not fp.exists() or not fp.is_file():
        return None

    try:
        lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, line - context)
        end = min(len(lines), line + context)
        chunk = []
        for i in range(start, end + 1):
            prefix = ">> " if i == line else "   "
            chunk.append(f"{prefix}{i:>4}: {lines[i - 1]}")
        return "\n".join(chunk)
    except Exception:
        return None
