"""Integration tests for the verification-as-a-job API flow.

These use ``httpx.AsyncClient`` against an ASGI transport so the test
runs inside the same event loop as the background tasks the API
creates with ``asyncio.create_task``. ``fastapi.testclient.TestClient``
spins up a new event loop per call, which orphans our background tasks
and is the wrong tool here.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from qallm.api import main as api_main
from qallm.api.routers import verification as api_verification
from qallm.jobs import _reset_store_for_tests


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=api_main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_state():
    _reset_store_for_tests()
    api_main.sessions.clear()
    yield
    api_main.sessions.clear()
    _reset_store_for_tests()


@pytest.fixture
def fake_session():
    sid = "test-session-1"
    api_main.sessions[sid] = {
        "orchestrator": None,
        "units": [],
        "analysed_units": {},
        "repaired_units": {},
        "analysis_rounds": [],
    }
    return sid


async def _poll_until(client, job_id: str, timeout: float = 3.0) -> dict:
    """Poll /api/jobs/{job_id} until it reaches a terminal status."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        res = await client.get(f"/api/jobs/{job_id}")
        body = res.json()
        if body["status"] in ("done", "error"):
            return body
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError(
                f"Job {job_id} did not finish within {timeout}s "
                f"(status={body['status']})"
            )
        await asyncio.sleep(0.02)


async def test_post_verification_run_returns_job_id_for_known_session(
    client, fake_session, monkeypatch
):
    monkeypatch.setattr(
        api_verification,
        "_run_verification_work",
        lambda sid: {"total_bugs": 0, "total_functions": 0, "functions": []},
    )
    res = await client.post(
        "/api/verification/run", json={"session_id": fake_session}
    )
    assert res.status_code == 200
    body = res.json()
    assert "job_id" in body
    assert body["session_id"] == fake_session
    assert body["status"] in {"pending", "running", "done"}


async def test_post_verification_run_returns_404_for_unknown_session(client):
    res = await client.post(
        "/api/verification/run", json={"session_id": "missing"}
    )
    assert res.status_code == 404


async def test_get_job_returns_404_for_unknown_id(client):
    res = await client.get("/api/jobs/not-a-real-job-id")
    assert res.status_code == 404


async def test_full_lifecycle_submit_poll_done(
    client, fake_session, monkeypatch
):
    expected_result = {
        "total_bugs": 3,
        "total_functions": 2,
        "functions": [{"function": "f1"}, {"function": "f2"}],
    }
    monkeypatch.setattr(
        api_verification, "_run_verification_work", lambda sid: expected_result
    )

    submit = await client.post(
        "/api/verification/run", json={"session_id": fake_session}
    )
    job_id = submit.json()["job_id"]
    body = await _poll_until(client, job_id)
    assert body["status"] == "done"
    assert body["result"] == expected_result
    assert body["error"] is None


async def test_full_lifecycle_submit_poll_error(
    client, fake_session, monkeypatch
):
    def boom(sid):
        raise RuntimeError("deliberate")

    monkeypatch.setattr(api_verification, "_run_verification_work", boom)

    submit = await client.post(
        "/api/verification/run", json={"session_id": fake_session}
    )
    job_id = submit.json()["job_id"]
    body = await _poll_until(client, job_id)
    assert body["status"] == "error"
    assert "RuntimeError" in body["error"]
    assert "deliberate" in body["error"]
    assert body["result"] is None


async def test_second_submission_for_active_session_returns_409(
    client, fake_session, monkeypatch
):
    import time

    def slow(sid):
        time.sleep(0.3)
        return {"total_bugs": 0, "total_functions": 0, "functions": []}

    monkeypatch.setattr(api_verification, "_run_verification_work", slow)

    first = await client.post(
        "/api/verification/run", json={"session_id": fake_session}
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/verification/run", json={"session_id": fake_session}
    )
    assert second.status_code == 409
    assert "already has an active job" in second.json()["detail"]

    # Drain the first so the autouse fixture cleanup is clean.
    await _poll_until(client, first.json()["job_id"], timeout=2.0)


async def test_list_session_jobs_returns_jobs_for_session(
    client, fake_session, monkeypatch
):
    monkeypatch.setattr(
        api_verification,
        "_run_verification_work",
        lambda sid: {"total_bugs": 0, "total_functions": 0, "functions": []},
    )

    first = (await client.post(
        "/api/verification/run", json={"session_id": fake_session}
    )).json()
    await _poll_until(client, first["job_id"])

    second = (await client.post(
        "/api/verification/run", json={"session_id": fake_session}
    )).json()
    await _poll_until(client, second["job_id"])

    listing = await client.get(f"/api/session/{fake_session}/jobs")
    assert listing.status_code == 200
    job_ids = {j["job_id"] for j in listing.json()["jobs"]}
    assert {first["job_id"], second["job_id"]} <= job_ids
