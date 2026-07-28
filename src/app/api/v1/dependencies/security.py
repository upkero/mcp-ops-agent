import secrets
from typing import Annotated

from fastapi import Depends, Header

from src.app.core.settings.security import SecuritySettings, get_security_settings
from src.app.exceptions.auth import UnauthorizedError


def require_api_key(
    settings: Annotated[SecuritySettings, Depends(get_security_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """Guard: enforce X-API-Key only when SECURITY_API_KEY is configured.

    Left open by default so the demo and MCP clients work without a key; set the
    env var to require it. Uses a constant-time comparison.
    """
    if settings.api_key is None:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise UnauthorizedError()
