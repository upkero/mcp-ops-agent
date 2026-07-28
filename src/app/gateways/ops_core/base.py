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
) -> httpx.Response:
    """Shared GET for every ops-core gateway (DRY): retry + uniform error mapping.

    A 404 means the caller asked for something that does not exist and is a typed
    OpsCoreNotFoundError. Use ``ops_core_get_optional`` where absence is an
    ordinary answer rather than a failure.
    """
    response = await _fetch(client, path, attempts=attempts, params=params)
    if response.status_code == 404:
        raise OpsCoreNotFoundError()
    return response


async def ops_core_get_optional(
    client: httpx.AsyncClient,
    path: str,
    *,
    attempts: int,
    params: Mapping[str, str | int] | None = None,
) -> httpx.Response | None:
    """Same as ``ops_core_get``, but a 404 is None rather than an error.

    Two functions instead of one ``allow_404`` flag: a boolean argument that
    changes the return type to ``Response | None`` makes every caller that never
    passes it prove to mypy that None cannot happen — which they did, with an
    ``assert`` each. Splitting the flag away deletes all three at once.
    """
    response = await _fetch(client, path, attempts=attempts, params=params)
    return None if response.status_code == 404 else response


async def _fetch(
    client: httpx.AsyncClient,
    path: str,
    *,
    attempts: int,
    params: Mapping[str, str | int] | None,
) -> httpx.Response:
    """Retry policy and error mapping, minus the 404 decision.

    Retries transport errors, 5xx, and rate-limit/unavailable (429/503) — the
    shared ``core/resilience`` policy honours ``Retry-After``. Any error response
    other than 404 becomes OpsCoreUnavailableError, so no gateway re-implements
    this policy.
    """

    # The decorator is applied here rather than at module level because `attempts`
    # is per-gateway configuration, not a constant of this module.
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

    if response.is_error and response.status_code != 404:
        # Non-retryable upstream response (e.g. 401 bad key, 422) → typed 502.
        raise OpsCoreUnavailableError(f"ops-core-api returned {response.status_code}.")
    return response
