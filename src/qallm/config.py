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
    # Per-request timeout for Ollama chat completions, in seconds. The
    # Ollama client library has no built-in timeout, so a slow or stuck
    # local server will block the worker thread indefinitely. 240s is
    # generous for typical local-model completions and tight enough to
    # catch genuine hangs.
    OLLAMA_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "240"))

    # SonarQube (optional). When SONARQUBE_URL and SONARQUBE_TOKEN are both
    # set, the SonarQubeAnalyzer runs and contributes higher-fidelity
    # reliability/security/maintainability ratings; otherwise it is a
    # no-op and the pipeline falls back to Radon/Bandit. Defaults target a
    # self-hosted Server (docker run sonarqube on :9000). Point the URL at
    # https://sonarcloud.io and set the organization to use SonarCloud
    # instead, no code change.
    SONARQUBE_URL: str | None = os.getenv("SONARQUBE_URL")
    SONARQUBE_TOKEN: str | None = os.getenv("SONARQUBE_TOKEN")
    SONARQUBE_ORGANIZATION: str | None = os.getenv("SONARQUBE_ORGANIZATION")
    # The sonar-scanner CLI binary; override if not on PATH.
    SONARQUBE_SCANNER: str = os.getenv("SONARQUBE_SCANNER", "sonar-scanner")
    # Seconds to wait for the scanner + the server's analysis to complete.
    SONARQUBE_TIMEOUT_SECONDS: float = float(
        os.getenv("SONARQUBE_TIMEOUT_SECONDS", "180")
    )

    # Directory where HumanEvalFix experiment runs are written and read
    # back for the Web-UI. Each subdirectory is one run (manifest.json,
    # results.jsonl, aggregates.json, report.md). Defaults to ./runs.
    QALLM_RUNS_DIR: str = os.getenv("QALLM_RUNS_DIR", "runs")

    # Directory where per-session reports are written by the orchestrator's
    # QualityReporter and read back for the Web-UI session library. Each
    # subdirectory is one processed session (summary.json, report.md, the
    # lineage/abandoned round artefacts). Must match the base_dir the
    # orchestrator uses for its reporter.
    QALLM_SESSIONS_DIR: str = os.getenv(
        "QALLM_SESSIONS_DIR", "outputs/quality_reporter"
    )

    # Budget caps. All are floors, not ceilings: code-level ceilings in
    # `qallm.cost` override these if they are too large. The intent is
    # that a typo in this file or an .env cannot blow the budget.
    TOKEN_BUDGET: int = int(os.getenv("TOKEN_BUDGET", "500000"))
    QALLM_MAX_ROUNDS: int = int(os.getenv("QALLM_MAX_ROUNDS", "5"))
    QALLM_MAX_SECONDS: int = int(os.getenv("QALLM_MAX_SECONDS", "1800"))
    QALLM_MAX_ROUND_SECONDS: int = int(os.getenv("QALLM_MAX_ROUND_SECONDS", "600"))
    QALLM_MAX_COST_USD: float = float(os.getenv("QALLM_MAX_COST_USD", "5.0"))


settings = Settings()
