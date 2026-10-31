from collections.abc import Mapping

import httpx

from src.app.core.resilience import retry_async
from src.app.exceptions.ops_core import OpsCoreNotFoundError, OpsCoreUnavailableError

# Transient failures worth retrying: network/timeout errors + upstream 5xx and 429.
_RETRYABLE: tuple[type[Exception], ...] = (httpx.TransportError, httpx.HTTPStatusError)


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
    if (response := await ops_core_get_optional(client, path, attempts=attempts, params=params)) is None:
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

    Two functions instead of one ``allow_404`` flag, so a caller that never expects
    None does not have to prove to mypy that it cannot happen.

    Retries transport errors, 5xx and 429 — the shared ``core/resilience`` policy
    honours ``Retry-After``. Any other error response becomes OpsCoreUnavailableError,
    so no gateway re-implements this policy.
    """

    # The decorator is applied here rather than at module level because `attempts`
    # is per-gateway configuration, not a constant of this module.
    # One target for every ops-core path: the path itself carries ids, and the httpx
    # client span already says which endpoint was retried.
    @retry_async(attempts=attempts, retry_on=_RETRYABLE, target="ops_core")
    async def _call() -> httpx.Response:
        response = await client.get(path, params=params)
        # Raise (retryable) for 5xx and 429; other 4xx are client problems where
        # retrying is pointless, so let them fall through to the mapping below.
        if response.status_code >= 500 or response.status_code == 429:
            response.raise_for_status()
        return response

    try:
        response = await _call()
    except httpx.HTTPError as exc:
        raise OpsCoreUnavailableError("Failed to reach ops-core-api.") from exc

    if response.status_code == 404:
        return None
    if response.is_error:
        # Non-retryable upstream response (e.g. 401 bad key, 422) → typed 502.
        raise OpsCoreUnavailableError(f"ops-core-api returned {response.status_code}.")
    return response
