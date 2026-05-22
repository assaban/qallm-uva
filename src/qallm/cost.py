"""Budget caps and cost estimation for the orchestrator loop.

Implements workflow design v3 section 6 and section 9.6.

Five orthogonal caps are enforced at QALLM round boundaries:

  * ``max_rounds``: how many QALLM rounds to run at most.
  * ``max_tokens``: total input + output tokens across the whole session.
  * ``max_seconds``: wall-clock time for the whole session.
  * ``max_round_seconds``: time for any single round.
  * ``max_cost_usd``: estimated USD cost across the whole session.

Each cap has two parts: a *default* (small, conservative; what an unconfigured
session uses) and a *ceiling* (the absolute maximum, regardless of any env-var
or CLI override). The user can lower below the default freely; they cannot
raise above the ceiling. The intent is that a config typo cannot blow a
budget through the floor.

Halt semantics
--------------

Caps are checked at *round boundaries*, not mid-round. When a cap trips, the
orchestrator finishes the current round (or current function within the
verification call) and halts before the next round. This means the actual
spend may slightly exceed the cap by the cost of the round that broke it.
This is intentional: hard mid-round interruption would require killing
pytest subprocesses and partial sessions, which is a worse failure mode
than going a little over.

Callers asking "did we halt or finish normally?" read the :class:`HaltReason`
enum on the summary object. ``HaltReason.COMPLETED`` means we ran to
``max_rounds`` without tripping anything else.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from qallm.llm.base import TokenTracker


# Ceilings: the absolute maximum any session can be configured to.
# These are not env-configurable; they live in code so a typo in a .env
# cannot raise them.
CEILING_ROUNDS = 10
CEILING_TOKENS = 2_000_000
CEILING_SECONDS = 3600           # one hour
CEILING_ROUND_SECONDS = 1200     # 20 minutes
CEILING_COST_USD = 25.00

# Defaults: the values an unconfigured session uses. Lower than the
# ceilings on purpose; the user has to opt up.
DEFAULT_ROUNDS = 5
DEFAULT_TOKENS = 500_000
DEFAULT_SECONDS = 1800           # 30 minutes
DEFAULT_ROUND_SECONDS = 600      # 10 minutes
DEFAULT_COST_USD = 5.00


class HaltReason(str, Enum):
    """Why a QALLM session stopped iterating."""

    COMPLETED = "completed"           # ran to max_rounds without tripping a cap
    MAX_ROUNDS = "max_rounds"
    MAX_TOKENS = "max_tokens"
    MAX_SECONDS = "max_seconds"
    MAX_ROUND_SECONDS = "max_round_seconds"
    MAX_COST_USD = "max_cost_usd"


def _clamp(value: int, ceiling: int, name: str) -> int:
    """Clamp ``value`` to ``ceiling`` with a noisy warning if clamped.

    ``value`` of 0 or less is treated as 'unset' and replaced with the
    ceiling, so users cannot accidentally configure an immediate halt.
    """
    if value <= 0:
        return ceiling
    if value > ceiling:
        import logging
        logging.getLogger(__name__).warning(
            "Requested %s=%d exceeds ceiling %d; clamping to ceiling.",
            name, value, ceiling,
        )
        return ceiling
    return value


def _clamp_float(value: float, ceiling: float, name: str) -> float:
    if value <= 0:
        return ceiling
    if value > ceiling:
        import logging
        logging.getLogger(__name__).warning(
            "Requested %s=%.2f exceeds ceiling %.2f; clamping to ceiling.",
            name, value, ceiling,
        )
        return ceiling
    return value


@dataclass(frozen=True)
class BudgetCaps:
    """The five caps that bound a session.

    Construct via :meth:`from_kwargs` to get ceiling-clamping and 0-handling
    for free. Direct construction is fine for tests but skips clamping.
    """

    max_rounds: int = DEFAULT_ROUNDS
    max_tokens: int = DEFAULT_TOKENS
    max_seconds: int = DEFAULT_SECONDS
    max_round_seconds: int = DEFAULT_ROUND_SECONDS
    max_cost_usd: float = DEFAULT_COST_USD

    @classmethod
    def from_kwargs(
        cls,
        *,
        max_rounds: int = DEFAULT_ROUNDS,
        max_tokens: int = DEFAULT_TOKENS,
        max_seconds: int = DEFAULT_SECONDS,
        max_round_seconds: int = DEFAULT_ROUND_SECONDS,
        max_cost_usd: float = DEFAULT_COST_USD,
    ) -> "BudgetCaps":
        return cls(
            max_rounds=_clamp(max_rounds, CEILING_ROUNDS, "max_rounds"),
            max_tokens=_clamp(max_tokens, CEILING_TOKENS, "max_tokens"),
            max_seconds=_clamp(max_seconds, CEILING_SECONDS, "max_seconds"),
            max_round_seconds=_clamp(
                max_round_seconds, CEILING_ROUND_SECONDS, "max_round_seconds"
            ),
            max_cost_usd=_clamp_float(
                max_cost_usd, CEILING_COST_USD, "max_cost_usd"
            ),
        )

    def to_dict(self) -> dict:
        return {
            "max_rounds": self.max_rounds,
            "max_tokens": self.max_tokens,
            "max_seconds": self.max_seconds,
            "max_round_seconds": self.max_round_seconds,
            "max_cost_usd": self.max_cost_usd,
        }


@dataclass
class BudgetState:
    """Mutable session state inspected at each round boundary.

    Owns the ``start_time``, the round count, and the last-round-start
    timestamp. The token tracker lives elsewhere (the LLM clients) and is
    passed in by reference.
    """

    caps: BudgetCaps
    tracker: TokenTracker
    start_time: float = field(default_factory=time.monotonic)
    round_start_time: float = field(default_factory=time.monotonic)
    rounds_completed: int = 0
    last_round_seconds: float = 0.0

    def mark_round_start(self) -> None:
        self.round_start_time = time.monotonic()

    def mark_round_end(self) -> None:
        now = time.monotonic()
        self.last_round_seconds = now - self.round_start_time
        self.rounds_completed += 1

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.start_time

    def check(self) -> Optional[HaltReason]:
        """Return a halt reason if any cap has tripped, else ``None``.

        Caps are checked in the order: rounds, cost, tokens, wall-clock,
        per-round. The first cap to trip wins, so the halt reason is
        deterministic even when multiple caps are over at once.
        """
        if self.rounds_completed >= self.caps.max_rounds:
            return HaltReason.MAX_ROUNDS

        if self.tracker.total_cost_usd >= self.caps.max_cost_usd:
            return HaltReason.MAX_COST_USD

        if self.tracker.total_tokens >= self.caps.max_tokens:
            return HaltReason.MAX_TOKENS

        if self.elapsed_seconds >= self.caps.max_seconds:
            return HaltReason.MAX_SECONDS

        if self.last_round_seconds >= self.caps.max_round_seconds:
            return HaltReason.MAX_ROUND_SECONDS

        return None

    def summary(self) -> dict:
        """Snapshot suitable for inclusion in summary.json."""
        return {
            "caps": self.caps.to_dict(),
            "rounds_completed": self.rounds_completed,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "last_round_seconds": round(self.last_round_seconds, 2),
            "tokens_used": self.tracker.total_tokens,
            "cost_usd": round(self.tracker.total_cost_usd, 6),
        }
