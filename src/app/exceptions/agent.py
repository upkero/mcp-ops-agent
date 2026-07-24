from src.app.exceptions.base import BaseAppException


class AgentError(BaseAppException):
    """Base exception for the orchestrator / MCP tool gateway."""

    error_code = "agent_error"
    default_detail = "Agent orchestration failed."


class ToolGatewayUnavailableError(AgentError):
    """Raised when the orchestrator cannot reach the MCP server over its transport.

    502 because the failing dependency is the (self-hosted) MCP endpoint the
    agent calls as a client — an upstream failure from the orchestrator's view.
    """

    status_code = 502
    error_code = "tool_gateway_unavailable"
    default_detail = "MCP tool gateway is unavailable."
