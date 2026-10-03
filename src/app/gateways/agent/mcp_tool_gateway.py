import json
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from src.app.contracts.agent.tool_catalog import ToolCallOutcome, ToolDefinition
from src.app.core.settings.agent import AgentSettings
from src.app.exceptions.agent import ToolGatewayUnavailableError
from src.app.interfaces.agent.tool_gateway import ToolGateway, ToolSession

logger = logging.getLogger(__name__)


class _McpToolSession(ToolSession):
    """Wraps a live MCP ClientSession as our transport-free ToolSession."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def list_tools(self) -> Sequence[ToolDefinition]:
        result = await self._session.list_tools()
        return [
            ToolDefinition(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema,
            )
            for tool in result.tools
        ]

    async def call_tool(self, name: str, arguments: Mapping[str, object]) -> ToolCallOutcome:
        result = await self._session.call_tool(name, dict(arguments))
        if result.isError:
            return ToolCallOutcome(content=self._safe_error(name, self._render(result)), is_error=True)
        return ToolCallOutcome(content=self._render(result), is_error=False)

    @staticmethod
    def _safe_error(name: str, raw: str) -> str:
        # FastMCP reports a failed tool as str(exception): pydantic's multi-line
        # report with library names and doc URLs, or an upstream status line. The
        # text goes to the model AND, verbatim, to the browser, so it is replaced
        # by a short fixed one; the original stays in the log.
        logger.warning("agent.tool_error", extra={"tool": name, "error": raw[:500]})
        if "validation error" in raw:
            return json.dumps({"error": "invalid_arguments", "detail": "The arguments do not match the tool's schema."})
        return json.dumps({"error": "tool_failed", "detail": "The tool could not complete the request."})

    @staticmethod
    def _render(result: Any) -> str:
        # Prefer the structured payload; fall back to concatenated text blocks.
        if result.structuredContent is not None:
            return json.dumps(result.structuredContent, ensure_ascii=False, default=str)
        texts = [
            getattr(block, "text", "")
            for block in result.content
            if getattr(block, "type", None) == "text"
        ]
        return "\n".join(text for text in texts if text)


class McpToolGateway(ToolGateway):
    """Adapter: ToolGateway backed by a real MCP client over Streamable HTTP.

    Connects to THIS server's own mounted /mcp endpoint (the self-loopback) using
    the official MCP SDK — the same protocol path an external Claude Desktop client
    uses. One short-lived session per agent run pairs with the stateless_http
    server: the initialize handshake is a single loopback round trip, dwarfed by
    LLM latency. Making the internal agent a genuine MCP client is what guarantees
    no tool executes outside the protocol.
    """

    def __init__(self, *, settings: AgentSettings) -> None:
        self._url = settings.mcp_self_url

    @asynccontextmanager
    async def open_session(self) -> AsyncIterator[ToolSession]:
        # NOTE: the X-Request-ID chain deliberately ends here. Outbound calls to
        # ops-core-api carry it (an httpx event hook in gateways/ops_core/client),
        # but this hop is the MCP SDK's own transport: streamable_http_client takes
        # no headers, only a whole httpx.AsyncClient, and supplying one means
        # re-creating the SDK's tuned defaults from a private helper and owning its
        # lifecycle — real coupling to buy a header on a loopback call that never
        # leaves the process. The tool call is already logged on both sides of it
        # under the incoming id, so the trace has no gap that matters.
        #
        # Only the connect/initialise phase is wrapped — errors from the yielded
        # body (the orchestrator's own logic) must propagate unchanged.
        async with (
            streamable_http_client(self._url) as (read, write, _get_session_id),
            ClientSession(read, write) as session,
        ):
            try:
                await session.initialize()
            except Exception as exc:
                raise ToolGatewayUnavailableError(
                    f"Failed to reach the MCP server at {self._url}."
                ) from exc
            yield _McpToolSession(session)
