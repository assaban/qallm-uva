"""Ollama local LLM model (Gemma, LLaMA, etc.)."""

from __future__ import annotations

import logging

from qallm.config import settings
from qallm.llm.base import LLMModel, LLMResponse, TokenTracker

logger = logging.getLogger(__name__)


class OllamaModel(LLMModel):
    def __init__(self, model_id: str | None = None) -> None:
        self._model_id = model_id or settings.OLLAMA_MODEL
        self.tracker: TokenTracker = TokenTracker(budget=199999999999)

    def name(self) -> str:
        return f"ollama/{self._model_id}"

    def token_tracker(self) -> TokenTracker:
        return self.tracker

    def is_configured(self) -> bool:
        base_url = settings.OLLAMA_BASE_URL
        if not base_url:
            return False
        try:
            import httpx
            with httpx.Client(timeout=2.0) as client:
                r = client.get(f"{base_url.rstrip('/')}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    def chat(self, system: str, user: str, tracker: TokenTracker | None = None) -> LLMResponse:
        from qallm.llm.transcript import timer

        if not settings.OLLAMA_BASE_URL:
            resp = LLMResponse(content="", provider="ollama", model=self._model_id,
                               error="OLLAMA_BASE_URL not set")
            self._capture(system, user, resp, 0.0)
            return resp

        if tracker and tracker.remaining <= 0:
            resp = LLMResponse(content="", provider="ollama", model=self._model_id,
                               error=f"Token budget exhausted ({tracker.budget} tokens used)")
            self._capture(system, user, resp, 0.0)
            return resp

        # Per-request timeout. The Ollama Python client defaults to no
        # timeout, which means a slow or stuck local server can block the
        # worker thread indefinitely. We bound the wait so a stuck call
        # fails cleanly rather than freezing the pipeline.
        #
        # 240s is generous for local gemma3:4b on a Mac CPU: a typical
        # test-generation completion is ~2k output tokens at 20-50 tok/s,
        # i.e. 40-100s. Genuine hangs (Ollama unresponsive, model not
        # loaded) trip well before this; legitimate slow calls finish in
        # time.
        timeout_seconds = float(getattr(settings, "OLLAMA_TIMEOUT_SECONDS", 240.0))

        with timer() as t:
            try:
                import ollama
                # Mark activity right before the (potentially minutes-long)
                # call so a watchdog gives this call a fresh window rather
                # than mistaking a slow local generation for a hang.
                if tracker:
                    tracker.beat()
                client = ollama.Client(
                    host=settings.OLLAMA_BASE_URL,
                    timeout=timeout_seconds,
                )
                response = client.chat(
                    model=self._model_id,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    options={"temperature": 0.1},
                )

                content = response.get("message", {}).get("content", "")
                resp = LLMResponse(
                    content=content,
                    input_tokens=response.get("prompt_eval_count", 0),
                    output_tokens=response.get("eval_count", 0),
                    model=self._model_id,
                    provider="ollama",
                )
            except Exception as e:
                # Includes httpx.ReadTimeout when the timeout above trips.
                # The error is surfaced through LLMResponse.error and bubbles
                # up to the orchestrator as "test generation failed", which
                # is much better than a thread frozen forever.
                logger.error("Ollama API error [%s]: %s", self._model_id, e)
                resp = LLMResponse(content="", provider="ollama", model=self._model_id, error=str(e))

        if tracker:
            tracker.record(resp)
        self._capture(system, user, resp, t.elapsed_ms)
        return resp
