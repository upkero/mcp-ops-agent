"""Tools route to services over genuine MCP JSON-RPC, and bad arguments are
rejected by the protocol before any service runs.

Uses the SDK's in-memory client<->server transport, so no network is involved —
but the request still travels the real MCP protocol into the FastMCP server and
out to a service backed by a mocked gateway.
"""

from unittest.mock import AsyncMock

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from src.app.bootstrap.container import ApplicationContainer
from src.app.contracts.ops_core.availability_slot import AvailabilitySlot
from src.app.interfaces.notifications.channel import NotificationChannel
from src.app.interfaces.ops_core.availability import AvailabilityGateway
from src.app.interfaces.ops_core.customers import CustomerGateway
from src.app.mcp.v1.server import build_mcp_server

_EXPECTED_TOOLS = {
    "check_calendar_availability",
    "lookup_customer",
    "calculate_quote",
    "list_services",
    "send_notification",
}


def _container_with_slots(slots: list[AvailabilitySlot]) -> ApplicationContainer:
    repo = AsyncMock(spec=AvailabilityGateway)
    repo.list_slots.return_value = slots
    container = ApplicationContainer()
    # Override the cached_property slot before first access (the DI test seam).
    container.__dict__["availability_gateway"] = repo
    return container


async def test_server_lists_the_five_tools() -> None:
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
            {"date": "2026-07-25", "time": "18:00", "resource_type": "table"},
        )

    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["available"] is True
    assert result.structuredContent["capacity"] == 4


# Each case is a call the model must NOT be able to make: FastMCP validates the
# typed tool arguments and returns an error result before the service is reached.
_INVALID_CALLS = [
    ("check_calendar_availability", {"date": "2026-07-25", "time": "18:00", "resource_type": "spaceship"}),
    ("check_calendar_availability", {"date": "not-a-date", "time": "18:00", "resource_type": "table"}),
    ("calculate_quote", {"service": "Deep Tissue Massage", "quantity": 0}),
    ("calculate_quote", {"service": "", "quantity": 1}),
    ("lookup_customer", {"name_or_id": ""}),
    ("send_notification", {"recipient": "Anna", "message": ""}),
    ("send_notification", {"recipient": "Anna", "message": "x" * 1001}),
    ("send_notification", {"recipient": "a" * 101, "message": "hi"}),
]


@pytest.mark.parametrize(("tool_name", "arguments"), _INVALID_CALLS)
async def test_invalid_arguments_are_rejected_by_the_protocol(
    tool_name: str, arguments: dict[str, object]
) -> None:
    server = build_mcp_server(ApplicationContainer())

    async with create_connected_server_and_client_session(server._mcp_server) as session:
        result = await session.call_tool(tool_name, arguments)

    assert result.isError is True


# ops-core-api's ResourceType values (contracts/enums.py). Keep in step with it: a value
# missing here makes the agent substitute another resource and answer confidently wrong.
_OPS_CORE_RESOURCE_TYPES = {"table", "meeting_room", "treatment_room"}


async def test_availability_tool_offers_every_ops_core_resource_type() -> None:
    server = build_mcp_server(ApplicationContainer())

    async with create_connected_server_and_client_session(server._mcp_server) as session:
        tools = {tool.name: tool for tool in (await session.list_tools()).tools}

    resource_type = tools["check_calendar_availability"].inputSchema["properties"]["resource_type"]
    assert set(resource_type["enum"]) == _OPS_CORE_RESOURCE_TYPES
    assert "treatment_room" in resource_type["description"]


async def test_notifying_a_stranger_is_reported_back_not_sent() -> None:
    gateway = AsyncMock(spec=CustomerGateway)
    gateway.search.return_value = []
    channel = AsyncMock(spec=NotificationChannel)
    container = ApplicationContainer()
    container.__dict__["customer_gateway"] = gateway
    container.__dict__["notification_channel"] = channel
    server = build_mcp_server(container)

    async with create_connected_server_and_client_session(server._mcp_server) as session:
        result = await session.call_tool(
            "send_notification", {"recipient": "+1-555-0199", "message": "Call us now"}
        )

    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["status"] == "rejected"
    channel.send.assert_not_awaited()
