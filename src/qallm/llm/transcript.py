"""LLM call transcript: capture every prompt and response for audit.

Every LLM call in QALLM funnels through ``LLMModel.chat(system, user)``.
That single seam is where this module hooks in, so the loop logic does
not change. The recorder captures, per call: the system and user prompt,
the raw response content, token usage, cost, latency, any error, and the
*context* in which the call was made (which round, stage, code unit,
function, and role).

This is the artefact that lets a reviewer answer, for any step of the
improvement loop, "what exactly did we ask the model, and what came
back?" Without it the prompts are constructed, sent, and discarded, and
the claim that the loop improves quality cannot be audited.

Design notes:

* Context is thread-local. The orchestrator sets it as it walks the loop
  (round/stage/unit/function/role); ``chat()`` reads it at call time.
  This avoids threading a new parameter through every provider signature
  and every caller.
* Capture is opt-in per run via ``TranscriptRecorder``. When no recorder
  is active, ``record()`` is a cheap no-op, so production paths that do
  not want transcripts pay almost nothing.
* Full prompt text can be large. The recorder stores it in memory and
  the reporter writes it to disk per round; callers that only want
  metadata can set ``store_prompts=False``.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator, Optional


@dataclass
class CallContext:
    """Where in the pipeline an LLM call happened.

    All fields are optional because some callers (e.g. ad-hoc scripts)
    invoke ``chat`` outside the loop. The orchestrator fills these in.
    """

    round_number: Optional[int] = None
    stage: Optional[str] = None          # analyse | repair | verify | judge
    role: Optional[str] = None           # repair | testgen | judge
    unit_id: Optional[str] = None
    function: Optional[str] = None
    oracle: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if not d["extra"]:
            d.pop("extra")
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class LLMCallRecord:
    """One captured LLM call: context, prompts, response, metrics."""

    seq: int
    context: dict[str, Any]
    system_prompt: str
    user_prompt: str
    response_content: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    model: str
    provider: str
    error: Optional[str]
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> dict[str, Any]:
        """Metadata only, no prompt/response bodies (for compact logs)."""
        d = self.to_dict()
        d.pop("system_prompt", None)
        d.pop("user_prompt", None)
        d.pop("response_content", None)
        d["system_prompt_chars"] = len(self.system_prompt)
        d["user_prompt_chars"] = len(self.user_prompt)
        d["response_chars"] = len(self.response_content)
        return d


class TranscriptRecorder:
    """Collects LLMCallRecords for one run. Thread-safe append."""

    def __init__(self, store_prompts: bool = True) -> None:
        self.store_prompts = store_prompts
        self._records: list[LLMCallRecord] = []
        self._lock = threading.Lock()
        self._seq = 0

    def add(self, record: LLMCallRecord) -> None:
        with self._lock:
            self._records.append(record)

    def next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    @property
    def records(self) -> list[LLMCallRecord]:
        with self._lock:
            return list(self._records)

    def for_round(self, round_number: int) -> list[LLMCallRecord]:
        return [r for r in self.records
                if r.context.get("round_number") == round_number]

    def to_list(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.records]

    def summaries(self) -> list[dict[str, Any]]:
        return [r.summary() for r in self.records]


# ─── Thread-local active recorder and context ───────────────────────
# The orchestrator activates a recorder for the duration of a run and
# updates the context as it walks the loop. chat() reads both.

_local = threading.local()


def _get_recorder() -> Optional[TranscriptRecorder]:
    return getattr(_local, "recorder", None)


def _get_context() -> CallContext:
    ctx = getattr(_local, "context", None)
    if ctx is None:
        ctx = CallContext()
        _local.context = ctx
    return ctx


@contextmanager
def active_recorder(recorder: TranscriptRecorder) -> Iterator[TranscriptRecorder]:
    """Activate a recorder for the current thread for the duration of a run."""
    prev = getattr(_local, "recorder", None)
    _local.recorder = recorder
    try:
        yield recorder
    finally:
        _local.recorder = prev


def set_context(**fields: Any) -> None:
    """Update the current thread's call context (merges with existing)."""
    ctx = _get_context()
    for key, value in fields.items():
        if key == "extra" and isinstance(value, dict):
            ctx.extra.update(value)
        elif hasattr(ctx, key):
            setattr(ctx, key, value)
        else:
            ctx.extra[key] = value


def reset_context() -> None:
    _local.context = CallContext()


@contextmanager
def call_context(**fields: Any) -> Iterator[None]:
    """Temporarily set context fields, restoring the previous values after.

    Used to scope a sub-call (e.g. a single repair) without leaking its
    role/function into later calls.
    """
    ctx = _get_context()
    saved = CallContext(**{k: getattr(ctx, k) for k in (
        "round_number", "stage", "role", "unit_id", "function", "oracle")},
        extra=dict(ctx.extra))
    set_context(**fields)
    try:
        yield
    finally:
        _local.context = saved


def record_call(
    *,
    system: str,
    user: str,
    content: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: float,
    model: str,
    provider: str,
    error: Optional[str],
) -> None:
    """Record one LLM call against the active recorder, if any.

    Called from inside ``chat()``. A no-op when no recorder is active, so
    the overhead on non-instrumented runs is a single attribute lookup.
    """
    recorder = _get_recorder()
    if recorder is None:
        return
    ctx = _get_context()
    keep_prompts = recorder.store_prompts
    rec = LLMCallRecord(
        seq=recorder.next_seq(),
        context=ctx.to_dict(),
        system_prompt=system if keep_prompts else "",
        user_prompt=user if keep_prompts else "",
        response_content=content if keep_prompts else "",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        model=model,
        provider=provider,
        error=error,
        timestamp=time.time(),
    )
    recorder.add(rec)


class _Timer:
    """Context manager returning elapsed milliseconds."""

    def __enter__(self) -> "_Timer":
        self._start = time.perf_counter()
        self.elapsed_ms = 0.0
        return self

    def __exit__(self, *exc: Any) -> None:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000.0


def timer() -> _Timer:
    return _Timer()
