from src.app.exceptions.base import BaseAppException


class OpsCoreError(BaseAppException):
    """Base exception for ops-core-api access."""

    error_code = "ops_core_error"
    default_detail = "ops-core-api operation failed."


class OpsCoreUnavailableError(OpsCoreError):
    """Raised when ops-core-api is unreachable or returns a non-recoverable error.

    Surfaces as a 502 (upstream failure) rather than a 500, so a flaky or
    misconfigured backend reads as "upstream unavailable", not an internal crash.
    """

    status_code = 502
    error_code = "ops_core_unavailable"
    default_detail = "ops-core-api is unavailable."


class OpsCoreNotFoundError(OpsCoreError):
    """Raised when a requested ops-core-api resource does not exist (HTTP 404).

    A genuine business outcome (e.g. an unknown service name in a quote), kept
    distinct from transport failures so callers can react differently.
    """

    status_code = 404
    error_code = "ops_core_not_found"
    default_detail = "Requested resource was not found in ops-core-api."
