"""Centralised configuration via environment variables.

No pydantic, no YAML, no complexity. Just os.getenv with sensible defaults.
"""

import os


class Settings:
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    # OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5-mini")

    ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gemma3:4b")

    TOKEN_BUDGET: int = int(os.getenv("TOKEN_BUDGET", "50000"))


settings = Settings()
