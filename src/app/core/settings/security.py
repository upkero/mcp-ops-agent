from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecuritySettings(BaseSettings):
    """Optional API-key protection for the public HTTP surface.

    When ``api_key`` is unset the HTTP routes are open (convenient for a local
    demo / connecting an MCP client). Set it in any real deployment to require an
    ``X-API-Key`` header on ``POST /mcp-tools/invoke``.
    """

    api_key: str | None = Field(
        default=None,
        min_length=16,
        description="If set, required as the X-API-Key header on /mcp-tools/invoke.",
    )

    model_config = SettingsConfigDict(
        env_prefix="SECURITY_",
        env_file=".env",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_security_settings() -> SecuritySettings:
    return SecuritySettings()
