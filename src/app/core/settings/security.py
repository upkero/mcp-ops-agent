from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecuritySettings(BaseSettings):
    """Auth settings for this service's own HTTP surface.

    Callers must present ``api_key`` in the ``X-API-Key`` header on
    ``POST /api/v1/invoke``. Required (min length 16): an optional key meant a
    renamed or forgotten variable left a paid endpoint silently open; a required
    one fails the boot instead. The MCP endpoint ``/mcp`` is not gated by it.
    """

    api_key: SecretStr = Field(
        ...,
        min_length=16,
        description="Required as the X-API-Key header on POST /api/v1/invoke.",
    )

    model_config = SettingsConfigDict(
        env_prefix="SECURITY_",
        env_file=".env",
        extra="ignore",
        # A too-short key would otherwise be echoed back in the boot-time validation error.
        hide_input_in_errors=True,
    )


@lru_cache(maxsize=1)
def get_security_settings() -> SecuritySettings:
    return SecuritySettings()
