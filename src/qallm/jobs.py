"""In-memory background job store for the QALLM web API.

Long-running pipeline steps (verification in particular, repair and full
analysis sessions in the future) are wrapped as :class:`Job` instances so
the HTTP layer can return immediately and the frontend can poll.

Design constraints, deliberate:

* Single-process, single-host. The store is a dict guarded by an
  ``asyncio.Lock``. There is no Redis, no Celery, no persistence. If the
  FastAPI process restarts mid-run, in-flight jobs are lost. This is
  documented and acceptable for the v1 thesis demo.

* One active job per session. Submitting a second job for a session that
  already has a PENDING or RUNNING job raises :class:`JobConflictError`,
  which the API layer maps to HTTP 409.

* Both async coroutines and sync callables can be backgrounded.
  :func:`submit_async` takes a coroutine factory; :func:`submit_sync`
  takes a callable and runs it via ``run_in_threadpool`` so it does not
  block the event loop. Either way you get a :class:`Job` back.

* Failures inside the work are captured on the job (``status=ERROR``,
  ``error`` populated) and never escape to the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

from fastapi.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class JobConflictError(Exception):
    """Raised when a session already has an active job."""


@dataclass
class Job:
    """A unit of background work.

    The ``result`` field is whatever the work returned (any JSON-friendly
    payload) when the job finishes successfully. ``error`` carries the
    string representation of any exception that escaped the work.
    """

    job_id: str
    session_id: str
    kind: str
    status: JobStatus = JobStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: Any = None
    error: str | None = None
    # Internal: the asyncio task running the work. Not serialised.
    _task: asyncio.Task | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "session_id": self.session_id,
            "kind": self.kind,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class JobStore:
    """In-memory job store guarded by an asyncio lock.

    The lock makes the conflict check (`is there an active job for this
    session?`) and the insert atomic with respect to other handlers on
    the same event loop. The lock is fine-grained enough that polling
    (`get`) does not contend with submission for long.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()

    async def submit_async(
        self,
        session_id: str,
        kind: str,
        work: Callable[[], Awaitable[Any]],
    ) -> Job:
        """Submit a coroutine factory as a background job.

        ``work`` must be a zero-argument callable returning an awaitable.
        We accept a factory rather than a coroutine so the coroutine is
        constructed inside the runner where its frame lives for the
        whole life of the task.
        """
        return await self._submit(session_id, kind, _async_runner(work))

    async def submit_sync(
        self,
        session_id: str,
        kind: str,
        work: Callable[[], Any],
    ) -> Job:
        """Submit a synchronous callable as a background job.

        The callable is executed in FastAPI's thread pool via
        ``run_in_threadpool``, so it does not block the event loop. Use
        this for orchestrator calls that are sync today.
        """
        return await self._submit(session_id, kind, _sync_runner(work))

    async def _submit(
        self,
        session_id: str,
        kind: str,
        runner: Callable[[Job], Awaitable[None]],
    ) -> Job:
        async with self._lock:
            active = self._active_for_session_locked(session_id)
            if active is not None:
                raise JobConflictError(
                    f"Session {session_id} already has an active job "
                    f"({active.job_id}, status={active.status.value})."
                )
            job = Job(
                job_id=str(uuid.uuid4()),
                session_id=session_id,
                kind=kind,
            )
            self._jobs[job.job_id] = job
            job._task = asyncio.create_task(runner(job))
        return job

    async def get(self, job_id: str) -> Job | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def list_for_session(self, session_id: str) -> list[Job]:
        async with self._lock:
            return [j for j in self._jobs.values() if j.session_id == session_id]

    async def active_for_session(self, session_id: str) -> Job | None:
        async with self._lock:
            return self._active_for_session_locked(session_id)

    def _active_for_session_locked(self, session_id: str) -> Job | None:
        for j in self._jobs.values():
            if j.session_id != session_id:
                continue
            if j.status in (JobStatus.PENDING, JobStatus.RUNNING):
                return j
        return None

    async def clear(self) -> None:
        """Cancel all in-flight jobs and forget them. Test-only."""
        async with self._lock:
            for job in self._jobs.values():
                if job._task is not None and not job._task.done():
                    job._task.cancel()
            self._jobs.clear()


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------


def _async_runner(
    work: Callable[[], Awaitable[Any]],
) -> Callable[[Job], Awaitable[None]]:
    async def runner(job: Job) -> None:
        job.status = JobStatus.RUNNING
        job.started_at = time.time()
        try:
            job.result = await work()
            job.status = JobStatus.DONE
        except Exception as exc:  # noqa: BLE001 - captured on the job
            logger.exception("Job %s (%s) failed", job.job_id, job.kind)
            job.error = f"{type(exc).__name__}: {exc}"
            job.status = JobStatus.ERROR
        finally:
            job.finished_at = time.time()

    return runner


def _sync_runner(
    work: Callable[[], Any],
) -> Callable[[Job], Awaitable[None]]:
    async def runner(job: Job) -> None:
        job.status = JobStatus.RUNNING
        job.started_at = time.time()
        try:
            job.result = await run_in_threadpool(work)
            job.status = JobStatus.DONE
        except Exception as exc:  # noqa: BLE001 - captured on the job
            logger.exception("Job %s (%s) failed", job.job_id, job.kind)
            job.error = f"{type(exc).__name__}: {exc}"
            job.status = JobStatus.ERROR
        finally:
            job.finished_at = time.time()

    return runner


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


_store: JobStore | None = None


def get_store() -> JobStore:
    """Return the process-wide :class:`JobStore`.

    Created lazily so importing this module does not require a running
    event loop (the lock construction inside ``JobStore`` is fine, but
    we defer just in case future versions hook into the loop earlier).
    """
    global _store
    if _store is None:
        _store = JobStore()
    return _store


def _reset_store_for_tests() -> None:
    """Test-only: drop the singleton so the next call gets a fresh store."""
    global _store
    _store = None


__all__ = [
    "Job",
    "JobConflictError",
    "JobStatus",
    "JobStore",
    "get_store",
]
