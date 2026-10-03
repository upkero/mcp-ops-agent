from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.app.bootstrap.container import ApplicationContainer
from src.app.interfaces.llm.llm_client import LLMClient
from src.app.interfaces.ops_core.health import OpsCoreHealthChecker
from src.main import create_app


def _app(*, llm_ok: bool, ops_core_ok: bool) -> FastAPI:
    llm = AsyncMock(spec=LLMClient)
    llm.ping.return_value = llm_ok
    probe = AsyncMock(spec=OpsCoreHealthChecker)
    probe.ping.return_value = ops_core_ok

    container = ApplicationContainer()
    container.__dict__["llm_client"] = llm
    container.__dict__["ops_core_health_probe"] = probe
    return create_app(container=container)


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


async def test_liveness_is_ok_even_with_every_upstream_down() -> None:
    # The point of the split: OpenAI being unreachable is not a reason to restart
    # this container, and the Dockerfile HEALTHCHECK hits exactly this path.
    response = await _get(_app(llm_ok=False, ops_core_ok=False), "/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_ok_when_both_upstreams_reachable() -> None:
    response = await _get(_app(llm_ok=True, ops_core_ok=True), "/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_503_when_ops_core_down_and_names_it() -> None:
    response = await _get(_app(llm_ok=True, ops_core_ok=False), "/health/ready")

    assert response.status_code == 503
    assert "ops-core-api" in response.json()["detail"]


async def test_readiness_503_when_the_llm_is_down_and_names_it() -> None:
    response = await _get(_app(llm_ok=False, ops_core_ok=True), "/health/ready")

    assert response.status_code == 503
    assert "llm" in response.json()["detail"]


async def test_a_misconfiguration_fails_the_boot_not_the_first_request(monkeypatch: pytest.MonkeyPatch) -> None:
    # A container property that cannot be built stands in for any misconfiguration.
    def broken(self: ApplicationContainer) -> None:
        raise RuntimeError("misconfigured")

    monkeypatch.setattr(ApplicationContainer, "orchestrator", property(broken))
    app = create_app()

    with pytest.raises(RuntimeError, match="misconfigured"):
        async with app.router.lifespan_context(app):
            pass
