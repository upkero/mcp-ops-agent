import httpx

from src.app.interfaces.ops_core.health import OpsCoreHealthChecker


class OpsCoreHealthProbe(OpsCoreHealthChecker):
    """Adapter: pings ops-core-api's unauthenticated /health for readiness checks.

    Reuses the shared ops-core httpx client; any transport error just reads as
    "not reachable" (False) rather than propagating — a probe never throws.
    """

    _PATH = "/health"

    def __init__(self, *, client: httpx.AsyncClient) -> None:
        self._client = client

    async def ping(self) -> bool:
        try:
            response = await self._client.get(self._PATH)
        except httpx.HTTPError:
            return False
        return response.status_code == 200
