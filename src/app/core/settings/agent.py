from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Orchestrator + MCP self-loopback settings.

    ``mcp_self_url`` is the URL the internal orchestrator uses to reach THIS
    server's own mounted MCP endpoint over real Streamable HTTP — the same URL an
    external client (Claude Desktop) would use. Routing the internal agent through
    the network transport is what guarantees there is no tool path that bypasses
    the MCP protocol. The trailing slash is deliberate: the mount answers ``/mcp``
    with a 307 to ``/mcp/``, which every loopback call would otherwise pay.
    """

    max_steps: int = Field(
        default=6,
        ge=1,
        le=25,
        description="Max LLM turns before the agent loop stops requesting tools.",
    )
    run_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        description="Wall-clock budget for one whole agent run (LLM and tool calls together).",
    )
    max_tool_calls_per_step: int = Field(
        default=4,
        ge=1,
        le=20,
        description="Tool calls one LLM turn may have executed; the rest are refused.",
    )
    max_notifications_per_run: int = Field(
        default=3,
        ge=0,
        le=50,
        description="Max send_notification calls one agent run may make; further ones are refused.",
    )
    mcp_self_url: str = Field(
        default="http://localhost:8000/mcp/",
        description="URL of this server's own mounted MCP endpoint (Streamable HTTP).",
    )

    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=".env",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_agent_settings() -> AgentSettings:
    return AgentSettings()
