"""Observability for the improvement loop.

Goal: make every LLM interaction in the pipeline auditable, so we can judge
whether a round genuinely improved quality rather than trusting a verdict in
isolation. The scientifically important questions are: *what exactly did we
ask the model*, *what did it return*, and *which findings moved as a result*.

Design. Every LLM call in QALLM funnels through ``LLMModel.chat(system,
user)``. Rather than edit each provider, :class:`ObservedLLM` wraps any
``LLMModel`` and records each call: the system and user prompts, the raw
response, token usage, latency, and the *context* of the call (which round,
stage, code unit, function, and role). The context is supplied out-of-band
via a thread-local :class:`CallContext` that the orchestrator updates as it
moves through the loop, so no method signatures in the loop change.

The recorder keeps calls in memory (so the API can stream them to the UI)
and the reporter writes them to disk per round as ``transcript.json``.

Nothing here changes loop behaviour: the wrapper delegates to the wrapped
model and returns its response unchanged.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from qallm.llm.base import LLMModel, LLMResponse, TokenTracker


# ─── Call context (thread-local) ────────────────────────────────────────
# The loop runs one unit at a time on one thread (the worker thread in the
# web app, the main thread in the CLI), so thread-local context is a safe,
# low-friction way to attach "where are we in the loop" to each LLM call
# without threading arguments through generator/repair internals.


@dataclass
class CallContext:
    """Where in the improvement loop an LLM call originates."""

    round_number: int = 0
    stage: Optional[str] = None       # analyse | repair | verify | judge
    role: Optional[str] = None        # repair | testgen | judge (call purpose)
    unit_id: Optional[str] = None
    function_name: Optional[str] = None
    oracle: Optional[str] = None      # crash | property | metamorphic | feedback
    attempt: int = 0                  # round-within-function for test gen

    def copy(self) -> "CallContext":
        return CallContext(**asdict(self))


class _ContextHolder(threading.local):
    def __init__(self) -> None:
        self.ctx = CallContext()


_holder = _ContextHolder()


def current_context() -> CallContext:
    """The active call context for this thread (a fresh default if unset)."""
    return _holder.ctx


def set_context(ctx: CallContext) -> None:
    _holder.ctx = ctx


def update_context(**fields: Any) -> CallContext:
    """Patch named fields on the current thread's context, return it.

    Returns the previous context so callers can restore it if they want
    scoped updates; most callers in the loop just overwrite as they go.
    """
    prev = _holder.ctx.copy()
    for k, v in fields.items():
        setattr(_holder.ctx, k, v)
    return prev


# ─── Transcript records ─────────────────────────────────────────────────


@dataclass
class LLMCallRecord:
    """One captured LLM call: its context, prompts, response, and cost."""

    seq: int
    round_number: int
    stage: Optional[str]
    role: Optional[str]
    unit_id: Optional[str]
    function_name: Optional[str]
    oracle: Optional[str]
    attempt: int
    system_prompt: str
    user_prompt: str
    response_content: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str
    latency_ms: int
    error: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def redacted(self, max_chars: int = 0) -> dict[str, Any]:
        """Dict form, optionally truncating long prompt/response bodies.

        ``max_chars=0`` means no truncation (full transcript). The UI uses
        a non-zero cap for the list view and fetches full bodies on demand.
        """
        d = self.to_dict()
        if max_chars > 0:
            for key in ("system_prompt", "user_prompt", "response_content"):
                val = d[key] or ""
                if len(val) > max_chars:
                    d[key] = val[:max_chars] + f"\n... [truncated {len(val) - max_chars} chars]"
        return d


class TranscriptRecorder:
    """Collects :class:`LLMCallRecord` entries across a run.

    Thread-safe append (the worker thread writes; the API thread may read a
    snapshot for live streaming). Reads return copies so callers never see a
    list mutating under them.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: list[LLMCallRecord] = []
        self._seq = 0

    def record(
        self,
        ctx: CallContext,
        system: str,
        user: str,
        resp: LLMResponse,
        latency_ms: int,
    ) -> LLMCallRecord:
        with self._lock:
            self._seq += 1
            rec = LLMCallRecord(
                seq=self._seq,
                round_number=ctx.round_number,
                stage=ctx.stage,
                role=ctx.role,
                unit_id=ctx.unit_id,
                function_name=ctx.function_name,
                oracle=ctx.oracle,
                attempt=ctx.attempt,
                system_prompt=system,
                user_prompt=user,
                response_content=resp.content,
                input_tokens=resp.input_tokens or 0,
                output_tokens=resp.output_tokens or 0,
                model=resp.model,
                provider=resp.provider,
                latency_ms=latency_ms,
                error=resp.error,
            )
            self._calls.append(rec)
            return rec

    def all(self) -> list[LLMCallRecord]:
        with self._lock:
            return list(self._calls)

    def for_round(self, round_number: int) -> list[LLMCallRecord]:
        with self._lock:
            return [c for c in self._calls if c.round_number == round_number]

    def to_list(self, max_chars: int = 0) -> list[dict[str, Any]]:
        return [c.redacted(max_chars) for c in self.all()]

    def clear(self) -> None:
        with self._lock:
            self._calls.clear()
            self._seq = 0


# ─── Observing wrapper ──────────────────────────────────────────────────


class ObservedLLM(LLMModel):
    """Wraps an :class:`LLMModel`, recording every ``chat`` call.

    Delegates name/token_tracker/is_configured/chat to the wrapped model so
    it is a drop-in replacement. The only added behaviour is: time the call,
    capture the prompts and response with the current thread context, and
    append a record to the shared recorder. Behaviour and return value are
    identical to the wrapped model.
    """

    def __init__(self, inner: LLMModel, recorder: TranscriptRecorder) -> None:
        self._inner = inner
        self._recorder = recorder

    # Expose the wrapped model in case callers need the concrete type.
    @property
    def inner(self) -> LLMModel:
        return self._inner

    def name(self) -> str:
        return self._inner.name()

    def token_tracker(self) -> TokenTracker:
        return self._inner.token_tracker()

    def is_configured(self) -> bool:
        return self._inner.is_configured()

    def chat(
        self, system: str, user: str, tracker: TokenTracker | None = None
    ) -> LLMResponse:
        start = time.monotonic()
        resp = self._inner.chat(system, user, tracker)
        latency_ms = int((time.monotonic() - start) * 1000)
        try:
            self._recorder.record(current_context(), system, user, resp, latency_ms)
        except Exception:
            # Observability must never break the loop. Swallow recorder
            # errors; a missing transcript entry is preferable to a failed
            # repair round.
            pass
        return resp
