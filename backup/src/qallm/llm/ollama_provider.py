"""Ollama local LLM model (Gemma, LLaMA, etc.)."""

from __future__ import annotations

import logging

from qallm.config import settings
from qallm.llm.base import LLMModel, LLMResponse, TokenTracker

logger = logging.getLogger(__name__)


class OllamaModel(LLMModel):
    def __init__(self, model_id: str | None = None) -> None:
        self._model_id = model_id or settings.OLLAMA_MODEL

    def name(self) -> str:
        return f"ollama/{self._model_id}"

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
        if not settings.OLLAMA_BASE_URL:
            return LLMResponse(content="", provider="ollama", model=self._model_id,
                               error="OLLAMA_BASE_URL not set")

        if tracker and tracker.remaining <= 0:
            return LLMResponse(content="", provider="ollama", model=self._model_id,
                               error=f"Token budget exhausted ({tracker.budget} tokens used)")

        try:
            import ollama
            client = ollama.Client(host=settings.OLLAMA_BASE_URL)
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
            logger.error("Ollama API error [%s]: %s", self._model_id, e)
            resp = LLMResponse(content="", provider="ollama", model=self._model_id, error=str(e))

        if tracker:
            tracker.record(resp)
        return resp