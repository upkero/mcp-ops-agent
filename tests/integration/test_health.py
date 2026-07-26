from unittest.mock import AsyncMock

import httpx

from src.app.bootstrap.container import ApplicationContainer
from src.app.interfaces.llm.llm_client import LLMClient
from src.app.interfaces.ops_core.health import OpsCoreHealthChecker
from src.main import create_app


def _app(*, llm_ok: bool, ops_core_ok: bool) -> object:
    llm = AsyncMock(spec=LLMClient)
    llm.ping.return_value = llm_ok
    probe = AsyncMock(spec=OpsCoreHealthChecker)
    probe.ping.return_value = ops_core_ok

    container = ApplicationContainer()
    container.__dict__["llm_client"] = llm
    container.__dict__["ops_core_health_probe"] = probe
    return create_app(container=container)


async def _get_health(app: object) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/health")


async def test_health_ok_when_both_upstreams_reachable() -> None:
    response = await _get_health(_app(llm_ok=True, ops_core_ok=True))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "llm": True, "ops_core": True}


async def test_health_degraded_when_ops_core_down() -> None:
    response = await _get_health(_app(llm_ok=True, ops_core_ok=False))

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["ops_core"] is False
