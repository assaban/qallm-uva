"""Tests for qallm.cost (budget caps and cost estimation).

Coverage:

  * BudgetCaps construction: defaults, clamping above ceiling, zero-handling.
  * BudgetState.check: each cap trips, ordering of multi-trip cases.
  * BudgetState integration with TokenTracker.
  * Summary shape suitable for summary.json.

These tests do not call any LLM; they manipulate the tracker directly to
simulate cost accumulation.
"""

from __future__ import annotations

import time


from qallm.cost import (
    CEILING_COST_USD,
    CEILING_ROUNDS,
    DEFAULT_COST_USD,
    DEFAULT_ROUNDS,
    DEFAULT_TOKENS,
    BudgetCaps,
    BudgetState,
    HaltReason,
)
from qallm.llm.base import TokenTracker


# ---------- BudgetCaps construction ----------


class TestBudgetCapsConstruction:
    def test_defaults_match_module_constants(self):
        caps = BudgetCaps()
        assert caps.max_rounds == DEFAULT_ROUNDS
        assert caps.max_tokens == DEFAULT_TOKENS
        assert caps.max_cost_usd == DEFAULT_COST_USD

    def test_from_kwargs_passes_through_valid_values(self):
        caps = BudgetCaps.from_kwargs(
            max_rounds=3,
            max_tokens=100_000,
            max_seconds=60,
            max_round_seconds=30,
            max_cost_usd=1.0,
        )
        assert caps.max_rounds == 3
        assert caps.max_tokens == 100_000
        assert caps.max_cost_usd == 1.0

    def test_from_kwargs_clamps_above_ceiling(self):
        caps = BudgetCaps.from_kwargs(max_rounds=10_000)
        assert caps.max_rounds == CEILING_ROUNDS

    def test_from_kwargs_clamps_cost_above_ceiling(self):
        caps = BudgetCaps.from_kwargs(max_cost_usd=999.99)
        assert caps.max_cost_usd == CEILING_COST_USD

    def test_zero_and_negative_treated_as_ceiling(self):
        caps_zero = BudgetCaps.from_kwargs(max_rounds=0)
        caps_neg = BudgetCaps.from_kwargs(max_rounds=-5)
        assert caps_zero.max_rounds == CEILING_ROUNDS
        assert caps_neg.max_rounds == CEILING_ROUNDS

    def test_to_dict_round_trips_all_fields(self):
        caps = BudgetCaps.from_kwargs(
            max_rounds=3, max_tokens=100_000, max_seconds=60,
            max_round_seconds=30, max_cost_usd=1.5,
        )
        d = caps.to_dict()
        assert d == {
            "max_rounds": 3,
            "max_tokens": 100_000,
            "max_seconds": 60,
            "max_round_seconds": 30,
            "max_cost_usd": 1.5,
        }


# ---------- BudgetState ----------


def _state(**caps_kwargs) -> BudgetState:
    """Build a BudgetState with a fresh tracker for testing."""
    tracker = TokenTracker(budget=99_999_999)
    caps = BudgetCaps.from_kwargs(**caps_kwargs)
    return BudgetState(caps=caps, tracker=tracker)


class TestBudgetStateChecks:
    def test_fresh_state_does_not_halt(self):
        st = _state()
        assert st.check() is None

    def test_max_rounds_trips_after_completion(self):
        st = _state(max_rounds=2)
        st.mark_round_start()
        st.mark_round_end()
        st.mark_round_start()
        st.mark_round_end()
        assert st.check() is HaltReason.MAX_ROUNDS

    def test_max_rounds_does_not_trip_before(self):
        st = _state(max_rounds=2)
        st.mark_round_start()
        st.mark_round_end()
        assert st.check() is None

    def test_max_tokens_trips_on_tracker_state(self):
        st = _state(max_tokens=1000)
        st.tracker.total_input = 600
        st.tracker.total_output = 401
        assert st.check() is HaltReason.MAX_TOKENS

    def test_max_cost_usd_trips_on_tracker_state(self):
        st = _state(max_cost_usd=1.0)
        st.tracker.total_cost_usd = 1.0001
        assert st.check() is HaltReason.MAX_COST_USD

    def test_max_seconds_trips_on_elapsed(self):
        st = _state(max_seconds=1)
        # Roll back start_time by 2 seconds to simulate elapsed time.
        st.start_time = time.monotonic() - 2.0
        assert st.check() is HaltReason.MAX_SECONDS

    def test_max_round_seconds_trips_on_long_round(self):
        st = _state(max_round_seconds=1)
        # Simulate a round that lasted 5 seconds.
        st.last_round_seconds = 5.0
        assert st.check() is HaltReason.MAX_ROUND_SECONDS


class TestCheckOrdering:
    """When multiple caps would trip at the same check, the result is deterministic.

    The order is: rounds, cost, tokens, wall-clock, per-round. Rationale: rounds
    is the most natural completion signal; cost is what the user pays for and
    should override anything else.
    """

    def test_rounds_beats_cost(self):
        st = _state(max_rounds=1, max_cost_usd=0.01)
        st.mark_round_start()
        st.mark_round_end()
        st.tracker.total_cost_usd = 5.0
        assert st.check() is HaltReason.MAX_ROUNDS

    def test_cost_beats_tokens(self):
        st = _state(max_cost_usd=0.5, max_tokens=100)
        st.tracker.total_cost_usd = 1.0
        st.tracker.total_input = 500
        assert st.check() is HaltReason.MAX_COST_USD

    def test_tokens_beats_seconds(self):
        st = _state(max_tokens=100, max_seconds=1)
        st.tracker.total_input = 1000
        st.start_time = time.monotonic() - 10
        assert st.check() is HaltReason.MAX_TOKENS

    def test_seconds_beats_round_seconds(self):
        st = _state(max_seconds=1, max_round_seconds=1)
        st.start_time = time.monotonic() - 10
        st.last_round_seconds = 5.0
        assert st.check() is HaltReason.MAX_SECONDS


# ---------- BudgetState.summary() ----------


class TestBudgetStateSummary:
    def test_summary_shape(self):
        st = _state(max_rounds=5, max_cost_usd=10.0)
        st.mark_round_start()
        st.mark_round_end()
        st.tracker.total_input = 100
        st.tracker.total_output = 200
        st.tracker.total_cost_usd = 0.42

        summary = st.summary()
        assert summary["rounds_completed"] == 1
        assert summary["tokens_used"] == 300
        assert summary["cost_usd"] == 0.42
        assert "elapsed_seconds" in summary
        assert "last_round_seconds" in summary
        assert summary["caps"]["max_rounds"] == 5
        assert summary["caps"]["max_cost_usd"] == 10.0


# ---------- HaltReason as a string enum ----------


class TestHaltReason:
    def test_completed_is_distinct_from_max_rounds(self):
        # COMPLETED means the loop ran to its natural end without tripping
        # any cap. MAX_ROUNDS means the rounds cap was the binding constraint.
        # In practice the orchestrator sets MAX_ROUNDS on natural completion;
        # COMPLETED is reserved for future use where a model verdict says stop.
        assert HaltReason.COMPLETED.value != HaltReason.MAX_ROUNDS.value

    def test_all_reasons_serialise_as_strings(self):
        for r in HaltReason:
            assert isinstance(r.value, str)
            assert r.value  # not empty
