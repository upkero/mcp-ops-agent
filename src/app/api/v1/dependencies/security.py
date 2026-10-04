import secrets
from typing import Annotated

from fastapi import Depends, Header

from src.app.core.settings.security import SecuritySettings, get_security_settings
from src.app.exceptions.auth import UnauthorizedError


def require_api_key(
    settings: Annotated[SecuritySettings, Depends(get_security_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """Guard: require X-API-Key to match SECURITY_API_KEY, in constant time.

    Bytes, because compare_digest rejects non-ASCII strings.
    """
    expected = settings.api_key.get_secret_value()
    if not x_api_key or not secrets.compare_digest(x_api_key.encode(), expected.encode()):
        raise UnauthorizedError()
