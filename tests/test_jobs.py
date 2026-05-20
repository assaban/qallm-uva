"""Tests for qallm.jobs.

Covers:
  * Submit/lifecycle for both async and sync work.
  * Status transitions (PENDING -> RUNNING -> DONE/ERROR).
  * Error capture (exceptions don't escape; job.error is populated).
  * The 'one active job per session' constraint.
  * Listing and active-lookup helpers.
  * Serialisation.
"""

from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio

from qallm.jobs import (
    Job,
    JobConflictError,
    JobStatus,
    JobStore,
    _reset_store_for_tests,
    get_store,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def store():
    """A fresh JobStore per test (does not touch the module singleton)."""
    s = JobStore()
    yield s
    await s.clear()


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Make sure the module-level get_store() is fresh in every test."""
    _reset_store_for_tests()
    yield
    _reset_store_for_tests()


async def _wait_for(store: JobStore, job_id: str, *, timeout: float = 2.0) -> Job:
    """Poll the store until the job reaches a terminal status."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        job = await store.get(job_id)
        assert job is not None
        if job.status in (JobStatus.DONE, JobStatus.ERROR):
            return job
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError(
                f"Job {job_id} did not finish within {timeout}s "
                f"(status={job.status.value})"
            )
        await asyncio.sleep(0.01)


# ---------------------------------------------------------------------------
# Submit + lifecycle
# ---------------------------------------------------------------------------


async def test_submit_async_runs_coroutine_and_marks_done(store: JobStore):
    async def work():
        await asyncio.sleep(0.01)
        return {"value": 42}

    job = await store.submit_async("sess1", "verification", work)
    assert job.status in (JobStatus.PENDING, JobStatus.RUNNING)
    assert job.session_id == "sess1"
    assert job.kind == "verification"

    done = await _wait_for(store, job.job_id)
    assert done.status is JobStatus.DONE
    assert done.result == {"value": 42}
    assert done.error is None
    assert done.started_at is not None
    assert done.finished_at is not None
    assert done.finished_at >= done.started_at


async def test_submit_sync_runs_callable_and_marks_done(store: JobStore):
    def work():
        return [1, 2, 3]

    job = await store.submit_sync("sess1", "verification", work)
    done = await _wait_for(store, job.job_id)
    assert done.status is JobStatus.DONE
    assert done.result == [1, 2, 3]


async def test_async_work_exception_is_captured_as_error(store: JobStore):
    async def work():
        raise ValueError("boom")

    job = await store.submit_async("sess1", "verification", work)
    done = await _wait_for(store, job.job_id)
    assert done.status is JobStatus.ERROR
    assert done.result is None
    assert "ValueError" in done.error
    assert "boom" in done.error


async def test_sync_work_exception_is_captured_as_error(store: JobStore):
    def work():
        raise RuntimeError("nope")

    job = await store.submit_sync("sess1", "verification", work)
    done = await _wait_for(store, job.job_id)
    assert done.status is JobStatus.ERROR
    assert "RuntimeError" in done.error
    assert "nope" in done.error


# ---------------------------------------------------------------------------
# One active job per session
# ---------------------------------------------------------------------------


async def test_submitting_second_active_job_for_same_session_conflicts(
    store: JobStore,
):
    async def slow():
        await asyncio.sleep(0.5)
        return "ok"

    first = await store.submit_async("sess1", "verification", slow)
    assert first.status in (JobStatus.PENDING, JobStatus.RUNNING)

    with pytest.raises(JobConflictError) as info:
        await store.submit_async("sess1", "verification", slow)
    assert "sess1" in str(info.value)
    assert first.job_id in str(info.value)

    # Original finishes normally.
    done = await _wait_for(store, first.job_id, timeout=2.0)
    assert done.status is JobStatus.DONE


async def test_second_job_allowed_after_first_finishes(store: JobStore):
    async def fast():
        return 1

    first = await store.submit_async("sess1", "verification", fast)
    await _wait_for(store, first.job_id)

    second = await store.submit_async("sess1", "verification", fast)
    done = await _wait_for(store, second.job_id)
    assert done.status is JobStatus.DONE


async def test_second_job_allowed_after_first_errors(store: JobStore):
    async def broken():
        raise RuntimeError("fail")

    async def fine():
        return "ok"

    first = await store.submit_async("sess1", "verification", broken)
    await _wait_for(store, first.job_id)

    second = await store.submit_async("sess1", "verification", fine)
    done = await _wait_for(store, second.job_id)
    assert done.status is JobStatus.DONE
    assert done.result == "ok"


async def test_different_sessions_run_concurrently(store: JobStore):
    async def slow():
        await asyncio.sleep(0.1)
        return "ok"

    a = await store.submit_async("sess-a", "verification", slow)
    b = await store.submit_async("sess-b", "verification", slow)
    assert a.job_id != b.job_id

    da = await _wait_for(store, a.job_id)
    db = await _wait_for(store, b.job_id)
    assert da.status is JobStatus.DONE
    assert db.status is JobStatus.DONE


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


async def test_get_returns_none_for_unknown_job(store: JobStore):
    assert await store.get("not-a-real-job") is None


async def test_list_for_session_returns_jobs_for_that_session_only(
    store: JobStore,
):
    async def quick():
        return 1

    a1 = await store.submit_async("sess-a", "verification", quick)
    await _wait_for(store, a1.job_id)
    a2 = await store.submit_async("sess-a", "verification", quick)
    await _wait_for(store, a2.job_id)
    b1 = await store.submit_async("sess-b", "verification", quick)
    await _wait_for(store, b1.job_id)

    sess_a = await store.list_for_session("sess-a")
    sess_b = await store.list_for_session("sess-b")
    assert {j.job_id for j in sess_a} == {a1.job_id, a2.job_id}
    assert {j.job_id for j in sess_b} == {b1.job_id}


async def test_active_for_session_returns_none_when_no_active_job(
    store: JobStore,
):
    async def quick():
        return 1

    job = await store.submit_async("sess1", "verification", quick)
    await _wait_for(store, job.job_id)
    assert await store.active_for_session("sess1") is None


async def test_active_for_session_returns_running_job(store: JobStore):
    async def slow():
        await asyncio.sleep(0.2)
        return 1

    job = await store.submit_async("sess1", "verification", slow)
    active = await store.active_for_session("sess1")
    assert active is not None
    assert active.job_id == job.job_id
    await _wait_for(store, job.job_id)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


async def test_job_to_dict_is_json_serialisable(store: JobStore):
    async def work():
        return {"functions": ["f1", "f2"], "total_bugs": 3}

    job = await store.submit_async("sess1", "verification", work)
    done = await _wait_for(store, job.job_id)
    payload = done.to_dict()
    text = json.dumps(payload)
    loaded = json.loads(text)
    assert loaded["status"] == "done"
    assert loaded["result"] == {"functions": ["f1", "f2"], "total_bugs": 3}
    assert loaded["session_id"] == "sess1"
    assert loaded["error"] is None


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------


async def test_get_store_returns_same_instance_on_repeat_calls():
    a = get_store()
    b = get_store()
    assert a is b
