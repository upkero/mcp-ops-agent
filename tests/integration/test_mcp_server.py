"""Fast, hermetic check that tools route to services over genuine MCP JSON-RPC.

Uses the SDK's in-memory client<->server transport, so no network is involved —
but the request still travels the real MCP protocol into the FastMCP server and
out to a service backed by a mocked repository.
"""

from unittest.mock import AsyncMock

from mcp.shared.memory import create_connected_server_and_client_session

from src.app.bootstrap.container import ApplicationContainer
from src.app.contracts.ops_core.availability_slot import AvailabilitySlot
from src.app.interfaces.ops_core.availability import AvailabilityRepository
from src.app.mcp.v1.server import build_mcp_server

_EXPECTED_TOOLS = {
    "check_calendar_availability",
    "lookup_customer",
    "calculate_quote",
    "send_notification",
}


def _container_with_slots(slots: list[AvailabilitySlot]) -> ApplicationContainer:
    repo = AsyncMock(spec=AvailabilityRepository)
    repo.list_slots.return_value = slots
    container = ApplicationContainer()
    # Override the cached_property slot before first access (the DI test seam).
    container.__dict__["availability_repository"] = repo
    return container


async def test_server_lists_the_four_tools() -> None:
    server = build_mcp_server(ApplicationContainer())

    async with create_connected_server_and_client_session(server._mcp_server) as session:
        result = await session.list_tools()

    assert {tool.name for tool in result.tools} == _EXPECTED_TOOLS


async def test_tool_call_routes_through_to_the_service() -> None:
    container = _container_with_slots(
        [AvailabilitySlot("s1", "table", "2026-07-25", "18:00:00", 4, True)]
    )
    server = build_mcp_server(container)

    async with create_connected_server_and_client_session(server._mcp_server) as session:
        result = await session.call_tool(
            "check_calendar_availability",
            {"args": {"date": "2026-07-25", "time": "18:00", "resource_type": "table"}},
        )

    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["available"] is True
    assert result.structuredContent["capacity"] == 4


async def test_invalid_arguments_are_rejected_by_the_protocol() -> None:
    server = build_mcp_server(ApplicationContainer())

    async with create_connected_server_and_client_session(server._mcp_server) as session:
        result = await session.call_tool(
            "check_calendar_availability",
            {"args": {"date": "2026-07-25", "time": "18:00", "resource_type": "spaceship"}},
        )

    # Bad enum value never reaches the service — FastMCP validation flags an error.
    assert result.isError is True
