import pytest

from src.app.api.v1.dependencies.security import require_api_key
from src.app.core.settings.security import SecuritySettings
from src.app.exceptions.auth import UnauthorizedError

_KEY = "k" * 16


def test_open_when_no_key_configured() -> None:
    # No SECURITY_API_KEY → the guard is a no-op (demo-friendly).
    require_api_key(x_api_key=None, settings=SecuritySettings(api_key=None))


def test_missing_header_rejected_when_key_configured() -> None:
    with pytest.raises(UnauthorizedError):
        require_api_key(x_api_key=None, settings=SecuritySettings(api_key=_KEY))


def test_wrong_key_rejected() -> None:
    with pytest.raises(UnauthorizedError):
        require_api_key(x_api_key="wrong-key-000000", settings=SecuritySettings(api_key=_KEY))


def test_correct_key_accepted() -> None:
    require_api_key(x_api_key=_KEY, settings=SecuritySettings(api_key=_KEY))
