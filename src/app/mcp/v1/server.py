from mcp.server.fastmcp import FastMCP

from src.app.bootstrap.container import ApplicationContainer
from src.app.mcp.v1.tools import booking, customers, notifications, pricing


def build_mcp_server(container: ApplicationContainer) -> FastMCP:
    """Assemble the FastMCP server and register every versioned tool group.

    Mirrors ``api/v1/router.py``: the tools are declared exactly once, here, and
    every consumer (Claude Desktop, the internal orchestrator, the HTTP route)
    reaches them only through this one server over the MCP protocol — there is no
    parallel copy of the tools anywhere.

    ``stateless_http=True`` keeps each request self-contained (simplest for the
    self-loopback client); ``streamable_http_path="/"`` makes the mounted endpoint
    resolve to exactly ``/mcp`` (see ``main.create_app``).
    """
    mcp = FastMCP("ops-agent", stateless_http=True, streamable_http_path="/")
    booking.register(mcp, container)
    customers.register(mcp, container)
    pricing.register(mcp, container)
    notifications.register(mcp, container)
    return mcp
