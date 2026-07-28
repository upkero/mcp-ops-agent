"""The authentic Definition-of-Done proof, automated.

Boots the whole app on a real loopback port, then POSTs a compound request to
/api/v1/invoke. The orchestrator's real McpToolGateway self-connects to the
server's own mounted /mcp over genuine Streamable HTTP — so this exercises the
"no bypass" path end to end. ops-core stays mocked, so it is one live server in
process (CI-friendly).
"""

import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import uvicorn

from src.app.bootstrap.container import ApplicationContainer
from src.app.contracts.llm.llm_response import LLMResponse
from src.app.contracts.llm.tool_call import ToolCall
from src.app.contracts.ops_core.availability_slot import AvailabilitySlot
from src.app.contracts.ops_core.customer import Customer
from src.app.core.settings.agent import AgentSettings
from src.app.gateways.agent.mcp_tool_gateway import McpToolGateway
from src.app.interfaces.ops_core.availability import AvailabilityGateway
from src.app.interfaces.ops_core.customers import CustomerGateway
from src.main import create_app
from tests.fakes import ScriptedLLMClient


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


@asynccontextmanager
async def _serve(app: object, port: int) -> AsyncIterator[str]:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        while not server.started:
            await asyncio.sleep(0.02)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


def _parse_sse(body: str) -> list[tuple[str, str]]:
    frames: list[tuple[str, str]] = []
    for block in body.strip().split("\n\n"):
        event = data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = line[len("data:"):].strip()
        if event:
            frames.append((event, data))
    return frames


def _build_container(port: int) -> ApplicationContainer:
    availability = AsyncMock(spec=AvailabilityGateway)
    availability.list_slots.return_value = [
        AvailabilitySlot("s1", "table", "2026-07-25", "18:00:00", 4, True)
    ]
    customers = AsyncMock(spec=CustomerGateway)
    customers.search.return_value = [Customer("c1", "Anna Petrova", "active", None, None)]

    # Scripted agent: check the slot, then look up the customer, then answer.
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content="",
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="check_calendar_availability",
                        arguments='{"date": "2026-07-25", "time": "18:00", "resource_type": "table"}',
                    ),
                ),
            ),
            LLMResponse(
                content="",
                tool_calls=(
                    ToolCall(id="c2", name="lookup_customer", arguments='{"name_or_id": "Anna"}'),
                ),
            ),
            LLMResponse(content="The 18:00 table is free and I found Anna Petrova."),
        ]
    )

    container = ApplicationContainer()
    container.__dict__["availability_gateway"] = availability
    container.__dict__["customer_gateway"] = customers
    container.__dict__["llm_client"] = llm
    # The REAL gateway, pointed at this server's own /mcp over the loopback.
    container.__dict__["tool_gateway"] = McpToolGateway(
        settings=AgentSettings(mcp_self_url=f"http://127.0.0.1:{port}/mcp")
    )
    return container


async def test_compound_request_streams_two_tool_calls_and_a_final_answer() -> None:
    port = _free_port()
    app = create_app(container=_build_container(port))

    async with (
        _serve(app, port) as base_url,
        httpx.AsyncClient(base_url=base_url, timeout=30.0) as client,
    ):
        response = await client.post(
            "/api/v1/invoke",
            json={"message": "check the 18:00 table tomorrow and find Anna Petrova"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    frames = _parse_sse(response.text)
    event_types = [event for event, _ in frames]

    # Two sequential tool-call events (booking then customer), then a final answer.
    tool_calls = [data for event, data in frames if event == "tool_call"]
    assert len(tool_calls) == 2
    assert "check_calendar_availability" in tool_calls[0]
    assert "lookup_customer" in tool_calls[1]
    assert event_types[-1] == "final"
    assert "Anna Petrova" in frames[-1][1]
