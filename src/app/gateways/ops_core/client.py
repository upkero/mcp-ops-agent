import httpx
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from src.app.core.request_id import get_request_id
from src.app.core.settings.ops_core import OpsCoreSettings
from src.app.core.url_redaction import strip_query_from_span

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


def create_ops_core_http_client(
    settings: OpsCoreSettings, *, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    """The only place the ops-core-api HTTP client is built.

    One shared client (base URL, X-API-Key header, timeout) is injected into every
    ops-core gateway adapter: one connection pool and one auth config for all of
    them (DRY), mirroring how ``create_llm_client`` centralises SDK construction. ``transport``
    is for tests: it replaces the network, and the instrumentation still wraps it.
    """
    client = httpx.AsyncClient(
        base_url=settings.base_url.rstrip("/"),
        headers={_API_KEY_HEADER: settings.api_key.get_secret_value()},
        timeout=settings.timeout_seconds,
        event_hooks={"request": [_inject_request_id]},
        transport=transport,
    )
    # A client span per attempt and a `traceparent`, so ops-core-api's server span is a
    # child of this request's trace. The X-Request-ID hook stays: logs join on it. The span
    # keeps the path but not the query: a customer search carries the name that was typed.
    HTTPXClientInstrumentor().instrument_client(client, request_hook=strip_query_from_span)
    return client
