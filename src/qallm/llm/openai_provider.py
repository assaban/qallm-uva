"""OpenAI LLM models."""

from __future__ import annotations

import logging

from qallm.config import settings
from qallm.llm.base import LLMModel, LLMResponse, TokenTracker

logger = logging.getLogger(__name__)


class OpenAIModel(LLMModel):

    def __init__(self, model_id: str | None = None) -> None:
        self._model_id = model_id or settings.OPENAI_MODEL
        self._is_gpt5 = self._model_id.startswith("gpt-5")
        self.tracker: TokenTracker = TokenTracker(budget=199999999999)

    def token_tracker(self) -> TokenTracker:
        return self.tracker

    def name(self) -> str:
        return self._model_id
        # return f"openai/{self._model_id}"

    def is_configured(self) -> bool:
        return bool(settings.OPENAI_API_KEY)

    def chat(self, system: str, user: str, tracker: TokenTracker | None = None) -> LLMResponse:
        from qallm.llm.transcript import timer

        if not self.is_configured():
            resp = LLMResponse(content="", provider="openai", model=self._model_id,
                               error="OPENAI_API_KEY not configured")
            self._capture(system, user, resp, 0.0)
            return resp

        if tracker and tracker.remaining <= 0:
            resp = LLMResponse(content="", provider="openai", model=self._model_id,
                               error=f"Token budget exhausted ({tracker.budget} tokens used)")
            self._capture(system, user, resp, 0.0)
            return resp

        with timer() as t:
            try:
                import openai
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

                kwargs: dict = {
                    "model": self._model_id,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                }
                if self._is_gpt5:
                    kwargs["max_completion_tokens"] = 4096
                else:
                    kwargs["temperature"] = 0.1
                    kwargs["max_tokens"] = 4096

                response = client.chat.completions.create(**kwargs)
                choice = response.choices[0]
                usage = response.usage

                resp = LLMResponse(
                    content=choice.message.content or "",
                    input_tokens=usage.prompt_tokens if usage else 0,
                    output_tokens=usage.completion_tokens if usage else 0,
                    model=response.model,
                    provider="openai",
                )
            except Exception as e:
                logger.error("OpenAI API error [%s]: %s", self._model_id, e)
                resp = LLMResponse(content="", provider="openai", model=self._model_id, error=str(e))

        if tracker:
            tracker.record(resp)
        self._capture(system, user, resp, t.elapsed_ms)
        return resp
