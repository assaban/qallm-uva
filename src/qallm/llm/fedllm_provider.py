"""FedLLM (EGI federated LLM inference) models.

FedLLM exposes an OpenAI-compatible API (LiteLLM gateway in front of vLLM
backends), so it reuses the OpenAI provider's chat logic, token tracking,
and response handling, overriding only the endpoint, key, default model,
and provider label. See:
https://docs.egi.eu/documentation/803/users/ai/fedllm/

Configure via FEDLLM_API_KEY (required), and optionally FEDLLM_BASE_URL
(default https://llm.ai.egi.eu/v1) and FEDLLM_MODEL (default gpt-oss-120b).
"""

from __future__ import annotations

import logging

from qallm.config import settings
from qallm.llm.openai_provider import OpenAIModel

logger = logging.getLogger(__name__)


class FedLLMModel(OpenAIModel):

    def __init__(self, model_id: str | None = None) -> None:
        super().__init__(model_id or settings.FEDLLM_MODEL)

    def is_configured(self) -> bool:
        return bool(settings.FEDLLM_API_KEY)

    def _provider_label(self) -> str:
        return "fedllm"

    def _build_client(self):
        import openai
        return openai.OpenAI(
            api_key=settings.FEDLLM_API_KEY,
            base_url=settings.FEDLLM_BASE_URL,
        )
