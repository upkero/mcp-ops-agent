from collections.abc import Mapping

import httpx

from src.app.core.resilience import retry_async
from src.app.exceptions.ops_core import OpsCoreNotFoundError, OpsCoreUnavailableError

# Transient failures worth retrying: network/timeout errors + upstream 5xx.
_RETRYABLE: tuple[type[Exception], ...] = (httpx.TransportError, httpx.HTTPStatusError)
# Retryable status codes beyond 5xx: rate limiting and temporary unavailability.
_RETRYABLE_STATUS = frozenset({429, 503})


async def ops_core_get(
    client: httpx.AsyncClient,
    path: str,
    *,
    attempts: int,
    params: Mapping[str, str | int] | None = None,
    allow_404: bool = False,
) -> httpx.Response | None:
    """Shared GET for every ops-core adapter (DRY): retry + uniform error mapping.

    Retries transport errors, 5xx, and rate-limit/unavailable (429/503) — the shared
    ``core/resilience`` policy honours ``Retry-After``. A surviving 404 becomes None (when ``allow_404``)
    or OpsCoreNotFoundError; any other error response becomes OpsCoreUnavailableError,
    so no adapter re-implements this policy.
    """

    # The decorator is applied here rather than at module level because `attempts`
    # is per-adapter configuration, not a constant of this module.
    @retry_async(attempts=attempts, retry_on=_RETRYABLE)
    async def _call() -> httpx.Response:
        response = await client.get(path, params=params)
        # Raise (retryable) for 5xx and 429/503; other 4xx are client problems where
        # retrying is pointless, so let them fall through to the mapping below.
        if response.status_code >= 500 or response.status_code in _RETRYABLE_STATUS:
            response.raise_for_status()
        return response

    try:
        response = await _call()
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
