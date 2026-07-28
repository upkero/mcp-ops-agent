from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class AppSettings(BaseSettings):
    """Root application settings — HTTP-surface concerns only.

    This service carries NO database configuration: it stores nothing itself and
    delegates all data access to ops-core-api over HTTP.
    """

    # NoDecode stops the settings source from JSON-decoding this field, which it
    # does for any complex type before validators run. Without it a plain
    # "a,b" env value fails at parse time and split_comma_separated never sees it.
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        # Closed by default: an agent loop that costs money per call should not be
        # reachable from an arbitrary page until an origin is named on purpose.
        default=[],
        description="Allowed CORS origins, comma-separated in the environment. Restrict in production.",
    )
    invoke_rate_limit_per_minute: int = Field(
        default=20,
        gt=0,
        description="Per-IP cap on POST /api/v1/invoke. Bounds both abuse and LLM spend.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def split_comma_separated(cls, value: Any) -> Any:
        # pydantic-settings parses a bare list[str] env var as JSON, so a plain
        # "a,b" value would fail validation without this.
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    return AppSettings()
