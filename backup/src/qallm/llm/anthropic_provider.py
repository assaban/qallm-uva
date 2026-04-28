"""Anthropic Claude LLM model."""

from __future__ import annotations

import logging

from qallm.config import settings
from qallm.llm.base import LLMModel, LLMResponse, TokenTracker

logger = logging.getLogger(__name__)


class AnthropicModel(LLMModel):
    def __init__(self, model_id: str | None = None) -> None:
        self._model_id = model_id or settings.ANTHROPIC_MODEL

    def name(self) -> str:
        return self._model_id

    def is_configured(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY)

    def chat(self, system: str, user: str, tracker: TokenTracker | None = None) -> LLMResponse:
        if not self.is_configured():
            return LLMResponse(content="", provider="anthropic", model=self._model_id,
                               error="ANTHROPIC_API_KEY not configured")

        if tracker and tracker.remaining <= 0:
            return LLMResponse(content="", provider="anthropic", model=self._model_id,
                               error=f"Token budget exhausted ({tracker.budget} tokens used)")

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=self._model_id,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=0.1,
            )

            content = ""
            for block in response.content:
                if block.type == "text":
                    content += block.text

            usage = response.usage
            resp = LLMResponse(
                content=content,
                input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0,
                model=response.model,
                provider="anthropic",
            )
        except Exception as e:
            logger.error("Anthropic API error [%s]: %s", self._model_id, e)
            resp = LLMResponse(content="", provider="anthropic", model=self._model_id, error=str(e))

        if tracker:
            tracker.record(resp)
        return resp