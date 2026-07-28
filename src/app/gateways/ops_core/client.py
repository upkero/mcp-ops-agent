import httpx

from src.app.core.request_id import get_request_id
from src.app.core.settings.ops_core import OpsCoreSettings

_API_KEY_HEADER = "X-API-Key"
_REQUEST_ID_HEADER = "X-Request-ID"


async def _inject_request_id(request: httpx.Request) -> None:
    """Carry the caller's request id upstream, so one id spans both services.

    An event hook rather than a static header on the client: the client is built
    once at startup, but the id is per request, so it can only be read from the
    ContextVar at send time. ops-core-api reuses an incoming X-Request-ID, so its
    logs end up joinable with ours on a single value.
    """
    if request_id := get_request_id():
        request.headers[_REQUEST_ID_HEADER] = request_id


def create_ops_core_http_client(settings: OpsCoreSettings) -> httpx.AsyncClient:
    """Factory — the only place the ops-core-api HTTP client is constructed.

    One shared client (base URL, X-API-Key header, timeout) is injected into every
    ops-core gateway adapter: one connection pool and one auth config for all of
    them (DRY), mirroring how ``create_llm_client`` centralises SDK construction.
    """
    return httpx.AsyncClient(
        base_url=settings.base_url.rstrip("/"),
        headers={_API_KEY_HEADER: settings.api_key.get_secret_value()},
        timeout=settings.timeout_seconds,
        event_hooks={"request": [_inject_request_id]},
    )
