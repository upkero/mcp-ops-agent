from collections.abc import Mapping

import httpx

from src.app.core.retry import retry_async
from src.app.exceptions.ops_core import OpsCoreNotFoundError, OpsCoreUnavailableError

# Transient failures worth retrying: network/timeout errors + upstream 5xx.
_RETRYABLE: tuple[type[Exception], ...] = (httpx.TransportError, httpx.HTTPStatusError)


async def ops_core_get(
    client: httpx.AsyncClient,
    path: str,
    *,
    attempts: int,
    params: Mapping[str, str | int] | None = None,
    allow_404: bool = False,
) -> httpx.Response | None:
    """Shared GET for every ops-core adapter (DRY): retry + uniform error mapping.

    Retries only server-side failures (5xx / transport). A surviving 404 becomes
    None (when ``allow_404``) or OpsCoreNotFoundError; any other error response
    becomes OpsCoreUnavailableError — so no adapter re-implements this policy.
    """

    async def _call() -> httpx.Response:
        response = await client.get(path, params=params)
        # Raise (retryable) for 5xx; 4xx is a client problem — retrying is pointless.
        if response.status_code >= 500:
            response.raise_for_status()
        return response

    try:
        response = await retry_async(_call, attempts=attempts, base_delay=0.2, retry_on=_RETRYABLE)
    except httpx.HTTPError as exc:
        raise OpsCoreUnavailableError("Failed to reach ops-core-api.") from exc

    if response.status_code == 404:
        if allow_404:
            return None
        raise OpsCoreNotFoundError()
    if response.is_error:
        # Non-retryable upstream response (e.g. 401 bad key, 422) → typed 502.
        raise OpsCoreUnavailableError(f"ops-core-api returned {response.status_code}.")
    return response
