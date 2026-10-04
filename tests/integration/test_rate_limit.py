"""The cap on POST /api/v1/invoke, the endpoint that spends money.

`INVOKE_RATE_LIMIT_PER_MINUTE` is pinned to 5 in `tests/conftest.py`, so the
budget is exhausted in a handful of cheap requests. The orchestrator is a fake:
what is under test is the middleware, not the agent loop.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from src.app.bootstrap.container import ApplicationContainer
from src.app.contracts.agent.agent_event import AgentEvent
from src.main import create_app
from tests.conftest import AUTH

_LIMIT = 5


class _StubOrchestrator:
    """Answers immediately: no LLM, no MCP session, no tools."""

    async def run(self, user_message: str) -> AsyncIterator[AgentEvent]:
        yield AgentEvent(type="final", data={"content": "ok"})


def _app() -> FastAPI:
    container = ApplicationContainer()
    container.__dict__["orchestrator"] = _StubOrchestrator()
    return create_app(container=container)


async def _post(client: httpx.AsyncClient) -> httpx.Response:
    return await client.post("/api/v1/invoke", json={"message": "hello"})


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=AUTH) as client:
        yield client


async def test_requests_within_the_budget_pass_and_advertise_what_is_left(
    client: httpx.AsyncClient,
) -> None:
    response = await _post(client)

    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == str(_LIMIT)
    assert response.headers["X-RateLimit-Remaining"] == str(_LIMIT - 1)


async def test_exceeding_the_budget_returns_the_error_envelope_with_retry_after(
    client: httpx.AsyncClient,
) -> None:
    for _ in range(_LIMIT):
        assert (await _post(client)).status_code == 200

    response = await _post(client)

    assert response.status_code == 429
    # The envelope, not a raw 500: the middleware returns it instead of raising,
    # because exception handlers live inside the middleware stack.
    assert response.json()["error_code"] == "rate_limit_exceeded"
    assert "Retry-After" in response.headers


async def test_health_is_not_rate_limited(client: httpx.AsyncClient) -> None:
    for _ in range(_LIMIT + 2):
        assert (await client.get("/health/live")).status_code == 200
