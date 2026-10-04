import pytest
from pydantic import ValidationError

from src.app.api.v1.dependencies.security import require_api_key
from src.app.core.settings.llm import LLMSettings
from src.app.core.settings.security import SecuritySettings
from src.app.exceptions.auth import UnauthorizedError

_KEY = "k" * 16


def test_the_key_is_required() -> None:
    # Optional, a renamed or forgotten variable left the paid endpoint open.
    with pytest.raises(ValidationError):
        SecuritySettings(_env_file=None, api_key=None)


def test_missing_header_rejected_when_key_configured() -> None:
    with pytest.raises(UnauthorizedError):
        require_api_key(x_api_key=None, settings=SecuritySettings(api_key=_KEY))


def test_wrong_key_rejected() -> None:
    with pytest.raises(UnauthorizedError):
        require_api_key(x_api_key="wrong-key-000000", settings=SecuritySettings(api_key=_KEY))


def test_correct_key_accepted() -> None:
    require_api_key(x_api_key=_KEY, settings=SecuritySettings(api_key=_KEY))


def test_the_keys_do_not_appear_in_a_settings_repr() -> None:
    assert _KEY not in repr(SecuritySettings(api_key=_KEY))
    assert "sk-live-secret-value" not in repr(LLMSettings(model="m", api_key="sk-live-secret-value"))
