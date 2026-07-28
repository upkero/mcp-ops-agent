from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpsCoreSettings(BaseSettings):
    """Connection settings for the upstream ops-core-api.

    Connection concerns only — the agent reaches ops-core-api's booking, customer
    and pricing endpoints over HTTP with an API key.
    """

    base_url: str = Field(
        default="http://localhost:8000",
        description="Base URL of ops-core-api (WITHOUT the /api/v1 suffix).",
    )
    # SecretStr keeps the key out of logs and repr; it is unwrapped exactly once,
    # where the httpx client is built.
    api_key: SecretStr = Field(
        ...,
        min_length=16,
        description="API key sent as the X-API-Key header to ops-core-api.",
    )
    timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        description="HTTP timeout for ops-core-api calls in seconds.",
    )
    # Total tries including the first, not the number of repeats — the same
    # meaning every service in the portfolio gives OPS_CORE_MAX_ATTEMPTS, so the
    # value arrives ready to hand to the retry policy.
    max_attempts: int = Field(
        default=3,
        ge=1,
        description="Total attempts (including the first) for transient ops-core-api failures.",
    )

    model_config = SettingsConfigDict(
        env_prefix="OPS_CORE_",
        env_file=".env",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_ops_core_settings() -> OpsCoreSettings:
    # Required fields come from the environment. The pydantic mypy plugin knows
    # that, so no suppression is needed here.
    return OpsCoreSettings()
