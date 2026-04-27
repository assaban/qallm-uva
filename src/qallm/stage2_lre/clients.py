import os
import re
from abc import ABC, abstractmethod
from openai import OpenAI
from anthropic import Anthropic

class LLMClient(ABC):
    """Base class for all LLM providers with modular model names."""
    def __init__(self, model_name: str):
        self.model_name = model_name

    @abstractmethod
    def generate_test(self, system_prompt: str, user_prompt: str) -> str:
        pass

class OpenAIClient(LLMClient):
    def __init__(self, model_name="gpt-4o-mini"):
        super().__init__(model_name)
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def generate_test(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        return response.choices[0].message.content

class AnthropicClient(LLMClient):
    def __init__(self, model_name="claude-3-5-sonnet-20240620"):
        super().__init__(model_name)
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    def generate_test(self, system_prompt: str, user_prompt: str) -> str:
        message = self.client.messages.create(
            model=self.model_name,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        return message.content[0].text

class GemmaClient(LLMClient):
    def __init__(self, model_name="gemma2"):
        super().__init__(model_name)
        # Using OpenAI-compatible endpoint for local Ollama
        self.client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

    def generate_test(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        return response.choices[0].message.content