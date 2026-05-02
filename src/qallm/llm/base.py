"""Abstract base for LLM models.

Every provider must implement the LLMModel interface. The TokenTracker
accumulates usage and cost across the RL feedback loop for thesis cost
analysis (RQ1 benchmarking).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# USD per 1,000,000 tokens (input / output). Local models cost 0.
MODEL_RATES: dict[str, dict[str, float]] = {
    "gpt-4o-mini":      {"input": 0.15,  "output": 0.60},
    "gpt-4o":           {"input": 2.50,  "output": 10.00},
    "gpt-5-mini":       {"input": 2.50,  "output": 10.00},
    "gpt-5-nano":       {"input": 0.20,  "output": 1.25},
    "gpt-5.4-mini":     {"input": 0.75,  "output": 4.50},
    "gpt-5.4-nano":     {"input": 0.20,  "output": 1.25},
    "gpt-5.4":          {"input": 2.50,  "output": 15.00},
    "gpt-5.5":          {"input": 5.00,  "output": 30.00},
    "claude-haiku-3":   {"input": 0.25,  "output": 1.25},
    "claude-haiku-3.5": {"input": 0.80,  "output": 4.00},
    "claude-haiku-4.5": {"input": 1.00,  "output": 5.00},
    "claude-sonnet-4":  {"input": 3.00,  "output": 15.00},
    "claude-opus-4":    {"input": 15.00, "output": 75.00},
}

def calculate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = {"input": 0.0, "output": 0.0}
    for key, val in MODEL_RATES.items():
        if model.startswith(key):
            rates = val
            break
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


@dataclass
class LLMResponse:
    """Response from a single LLM call."""
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    provider: str = ""
    error: str | None = None


@dataclass
class TokenTracker:
    """Accumulates token usage and cost across multiple calls within a session."""
    budget: int = 0
    total_input: int = 0
    total_output: int = 0
    total_cost_usd: float = 0.0
    calls: int = 0
    errors: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.total_input + self.total_output

    @property
    def remaining(self) -> int:
        return max(0, self.budget - self.total_tokens)

    def record(self, resp: LLMResponse) -> None:
        self.calls += 1
        self.total_input += resp.input_tokens
        self.total_output += resp.output_tokens
        call_cost = calculate_cost_usd(resp.model, resp.input_tokens, resp.output_tokens)
        self.total_cost_usd += call_cost
        if resp.error:
            self.errors += 1
        self.history.append({
            "call": self.calls,
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "cost_usd": round(call_cost, 8),
            "model": resp.model,
            "provider": resp.provider,
            "error": resp.error,
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget,
            "total_input_tokens": self.total_input,
            "total_output_tokens": self.total_output,
            "total_tokens": self.total_tokens,
            "remaining": self.remaining,
            "total_cost_usd": round(self.total_cost_usd, 8),
            "calls": self.calls,
            "errors": self.errors,
        }


class LLMModel(ABC):
    """Interface every LLM model must implement."""

    @abstractmethod
    def name(self) -> str:
        """Display name (e.g. 'gpt-4o-mini')."""
    """Interface every LLM model must implement."""

    @abstractmethod
    def token_tracker(self) -> TokenTracker:
        """Returns the token tracker for the model."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the required API key / env vars are set."""

    @abstractmethod
    def chat(self, system: str, user: str, tracker: TokenTracker | None = None) -> LLMResponse:
        """Send a chat completion request and return the response."""
