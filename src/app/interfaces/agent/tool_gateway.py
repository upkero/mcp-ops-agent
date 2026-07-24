from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager

from src.app.contracts.agent.tool_catalog import ToolCallOutcome, ToolDefinition


class ToolSession(ABC):
    """One open MCP client session (protocol-level), scoped to a single agent run."""

    @abstractmethod
    async def list_tools(self) -> Sequence[ToolDefinition]:
        """List the tools the MCP server advertises."""

    @abstractmethod
    async def call_tool(self, name: str, arguments: Mapping[str, object]) -> ToolCallOutcome:
        """Invoke a tool over the MCP protocol and return its normalised result."""


class ToolGateway(ABC):
    """Adapter over an MCP client: a factory for short-lived tool sessions.

    ``open_session()`` yields a ToolSession bound to one real MCP connection; the
    orchestrator opens exactly one per run. The orchestrator depends on this
    interface, not on the MCP SDK — so a fake gateway drives unit tests and the
    real Streamable-HTTP gateway drives production, unchanged (Dependency
    Inversion). Making the internal agent a genuine MCP client is what guarantees
    no tool is ever executed outside the protocol.
    """

    @abstractmethod
    def open_session(self) -> AbstractAsyncContextManager[ToolSession]:
        """Open one MCP session as an async context manager."""
