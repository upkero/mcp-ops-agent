import httpx

from src.app.core.settings.ops_core import OpsCoreSettings

_API_KEY_HEADER = "X-API-Key"


def create_ops_core_http_client(settings: OpsCoreSettings) -> httpx.AsyncClient:
    """Factory — the only place the ops-core-api HTTP client is constructed.

    One shared client (base URL, X-API-Key header, timeout) is injected into every
    ops-core repository adapter: one connection pool and one auth config for all of
    them (DRY), mirroring how ``create_llm_client`` centralises SDK construction.
    """
    return httpx.AsyncClient(
        base_url=settings.base_url.rstrip("/"),
        headers={_API_KEY_HEADER: settings.api_key},
        timeout=settings.timeout_seconds,
    )
