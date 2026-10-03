"""Failures that never reach a route still leave in the standard envelope."""

from collections.abc import AsyncIterator
from uuid import UUID

import httpx

from src.app.bootstrap.container import ApplicationContainer
from src.app.contracts.agent.agent_event import AgentEvent
from src.main import create_app


class _StubOrchestrator:
    """The route resolves its dependency before the body; no LLM is needed here."""

    async def run(self, user_message: str) -> AsyncIterator[AgentEvent]:
        yield AgentEvent(type="final", data={"content": "ok"})


async def test_a_form_body_is_a_validation_error_not_a_crash() -> None:
    # curl's default content type when -H 'Content-Type: application/json' is
    # forgotten. Pydantic keeps the raw bytes in the error, undecodable ones too.
    container = ApplicationContainer()
    container.__dict__["orchestrator"] = _StubOrchestrator()
    transport = httpx.ASGITransport(app=create_app(container=container))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for body in (b"message=hi", b"\xff\xfe"):
            response = await client.post(
                "/api/v1/invoke",
                content=body,
                headers={"Content-Type": "application/x-www-form-urlencoded", "X-Request-ID": "abc-123"},
            )

            assert response.status_code == 422
            assert response.json()["error_code"] == "request_validation_error"
            assert response.headers["X-Request-ID"] == "abc-123"


async def test_an_unhandled_error_is_a_500_that_still_carries_the_request_id() -> None:
    async def boom() -> None:
        raise RuntimeError("boom")

    app = create_app()
    app.add_api_route("/boom", boom)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom", headers={"X-Request-ID": "abc-123"})

    assert response.status_code == 500
    assert response.json()["error_code"] == "internal_server_error"
    assert response.headers["X-Request-ID"] == "abc-123"


async def test_a_malformed_request_id_is_replaced() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Echoed, forwarded upstream and logged, so a markup or oversized id is replaced.
        for bad in ("attacker-<script>", "r" * 129):
            response = await client.get("/no-such-route", headers={"X-Request-ID": bad})

            assert UUID(response.headers["X-Request-ID"])
