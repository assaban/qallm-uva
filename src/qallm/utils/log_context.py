"""Per-unit logging context.

Across a run, many components log independently (orchestrator, analysis,
repair, verification manager/generator/executor/sandbox). Their messages name
the function under test but not *where in the run* it sits, so from a single
line you cannot tell whether you are on the first code unit or the last. That
makes a long run feel unobservable.

This module carries a small progress label in a ``contextvar`` that the
orchestrator sets once per code unit (e.g. ``unit 3/47 prediction.ipynb::7``).
A logging ``Filter`` then prefixes that label onto every record emitted while
the context is active, regardless of which component logged it. Components do
not need to thread any parameter through their call sites; they just log as
usual and inherit the context.

Usage (orchestrator):

    from qallm.utils.log_context import set_unit_context, clear_unit_context
    set_unit_context(index=i, total=n, unit_id="file.py::3")
    ...                     # all logs here are prefixed
    clear_unit_context()    # or use the unit_context() context manager

Install the filter once at logging setup:

    from qallm.utils.log_context import install_unit_context_filter
    install_unit_context_filter()
"""

from __future__ import annotations

import contextlib
import logging
from contextvars import ContextVar

# Holds the current prefix, e.g. "[unit 3/47 file.py::3]". Empty when no unit
# is being processed (setup, ingestion, teardown), in which case nothing is
# prefixed.
_unit_label: ContextVar[str] = ContextVar("qallm_unit_label", default="")


def set_unit_context(*, index: int, total: int, unit_id: str) -> None:
    """Set the progress label for the unit currently being processed.

    ``index`` is 1-based. ``unit_id`` is the stable ``path::cell`` identifier;
    the path is shortened to its basename to keep lines readable.
    """
    short = unit_id
    if "::" in unit_id:
        path, _, cell = unit_id.rpartition("::")
        base = path.rsplit("/", 1)[-1]
        short = f"{base}::{cell}"
    else:
        short = unit_id.rsplit("/", 1)[-1]
    _unit_label.set(f"[unit {index}/{total} {short}] ")


def clear_unit_context() -> None:
    """Clear the progress label (no prefix until the next set)."""
    _unit_label.set("")


@contextlib.contextmanager
def unit_context(*, index: int, total: int, unit_id: str):
    """Scope a unit's progress label to a ``with`` block."""
    token = _unit_label.set("")
    set_unit_context(index=index, total=total, unit_id=unit_id)
    try:
        yield
    finally:
        _unit_label.reset(token)


def current_unit_label() -> str:
    """The current prefix, or empty string when no unit context is set."""
    return _unit_label.get()


class _UnitContextFilter(logging.Filter):
    """Prefix the active unit label onto every record's message.

    A Filter (not a Formatter) is used so the prefix appears regardless of the
    handler's format string, and so it is a no-op when no context is set.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        label = _unit_label.get()
        if label and not getattr(record, "_unit_ctx_applied", False):
            record.msg = f"{label}{record.msg}"
            record._unit_ctx_applied = True
        return True


_FILTER_SINGLETON = _UnitContextFilter()


def install_unit_context_filter() -> None:
    """Attach the unit-context filter to the root logger (idempotent).

    Filters on the root logger do not propagate to child loggers' own
    handlers, so the filter is attached to the root *handlers*. When logging
    is configured with basicConfig (one root handler), this covers everything
    that propagates to root, which is the whole pipeline.
    """
    root = logging.getLogger()
    for handler in root.handlers:
        if _FILTER_SINGLETON not in handler.filters:
            handler.addFilter(_FILTER_SINGLETON)
