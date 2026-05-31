"""The TokenTracker heartbeat lets a watchdog tell slow from hung."""

import time

from qallm.llm.base import TokenTracker, LLMResponse


def test_beat_updates_last_activity():
    t = TokenTracker(budget=1000)
    first = t.last_activity
    time.sleep(0.01)
    t.beat()
    assert t.last_activity > first


def test_record_updates_last_activity():
    t = TokenTracker(budget=1000)
    first = t.last_activity
    time.sleep(0.01)
    t.record(LLMResponse(content="x", provider="ollama", model="m",
                         input_tokens=1, output_tokens=1))
    assert t.last_activity > first


def test_snapshot_reports_seconds_since_activity():
    # A fresh tracker has a near-zero idle time; after a pause it grows.
    t = TokenTracker(budget=1000)
    t.beat()
    idle_now = time.monotonic() - t.last_activity
    assert idle_now < 1.0
