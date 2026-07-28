import httpx

from src.app.core.request_id import set_request_id
from src.app.core.settings.ops_core import OpsCoreSettings
from src.app.gateways.ops_core.client import create_ops_core_http_client

_SETTINGS = OpsCoreSettings(api_key="test-ops-core-key-1234567890")


async def _sent_headers(request_id: str) -> httpx.Headers:
    set_request_id(request_id)
    client = create_ops_core_http_client(_SETTINGS)
    request = client.build_request("GET", "/api/v1/customers")
    for hook in client.event_hooks["request"]:
        await hook(request)
    return request.headers


async def test_the_incoming_request_id_travels_upstream() -> None:
    headers = await _sent_headers("abc-123")
    assert headers["X-Request-ID"] == "abc-123"
    # The key still goes out too — the hook adds a header, it does not replace them.
    assert headers["X-API-Key"] == "test-ops-core-key-1234567890"


async def test_no_request_id_means_no_header() -> None:
    """Outside a request (nothing set) the header is absent, not empty."""
    headers = await _sent_headers("")
    assert "X-Request-ID" not in headers
