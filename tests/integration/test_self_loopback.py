"""The authentic Definition-of-Done proof, automated.

Boots the whole app on a real loopback port, then POSTs a compound request to
/api/v1/invoke. The orchestrator's real McpToolGateway self-connects to the
server's own mounted /mcp over genuine Streamable HTTP — so this exercises the
"no bypass" path end to end. ops-core stays mocked, so it is one live server in
process (CI-friendly).
"""

import asyncio
import socket
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import uvicorn
from fastapi import FastAPI
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.app.bootstrap.container import ApplicationContainer
from src.app.contracts.agent.tool_catalog import ToolDefinition
from src.app.contracts.llm.llm_message import LLMMessage
from src.app.contracts.llm.llm_response import LLMResponse
from src.app.contracts.llm.tool_call import ToolCall
from src.app.contracts.ops_core.availability_slot import AvailabilitySlot
from src.app.contracts.ops_core.customer import Customer
from src.app.core.request_id import get_request_id
from src.app.core.settings.agent import AgentSettings
from src.app.gateways.agent.mcp_tool_gateway import McpToolGateway
from src.app.interfaces.ops_core.availability import AvailabilityGateway
from src.app.interfaces.ops_core.customers import CustomerGateway
from src.main import create_app
from tests.conftest import AUTH
from tests.fakes import ScriptedLLMClient


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


@asynccontextmanager
async def _serve(app: FastAPI, port: int) -> AsyncIterator[str]:
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


def _build_container(port: int, seen_ids: list[str] | None = None) -> ApplicationContainer:
    availability = AsyncMock(spec=AvailabilityGateway)
    slots = [AvailabilitySlot("s1", "table", "2026-07-25", "18:00:00", 4, True)]
    availability.list_slots.return_value = slots
    if seen_ids is not None:

        async def _record_request_id(*args: object, **kwargs: object) -> list[AvailabilitySlot]:
            seen_ids.append(get_request_id())
            return slots

        availability.list_slots.side_effect = _record_request_id
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
        settings=AgentSettings(mcp_self_url=f"http://127.0.0.1:{port}/mcp/")
    )
    return container


async def test_compound_request_streams_two_tool_calls_and_a_final_answer() -> None:
    port = _free_port()
    app = create_app(container=_build_container(port))

    async with (
        _serve(app, port) as base_url,
        httpx.AsyncClient(base_url=base_url, timeout=30.0, headers=AUTH) as client,
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


async def test_the_callers_request_id_reaches_the_tool_over_the_loopback() -> None:
    port = _free_port()
    seen_ids: list[str] = []
    app = create_app(container=_build_container(port, seen_ids))

    async with (
        _serve(app, port) as base_url,
        httpx.AsyncClient(base_url=base_url, timeout=30.0, headers=AUTH) as client,
    ):
        await client.post(
            "/api/v1/invoke",
            json={"message": "check the 18:00 table"},
            headers={"X-Request-ID": "trace-me-123"},
        )

    assert seen_ids == ["trace-me-123"]


async def test_the_default_loopback_url_is_served_without_a_redirect() -> None:
    port = _free_port()
    app = create_app(container=_build_container(port))
    url = AgentSettings().mcp_self_url.replace("localhost:8000", f"127.0.0.1:{port}")

    async with _serve(app, port), httpx.AsyncClient(follow_redirects=False) as client:
        response = await client.post(url, json={})

    assert url.endswith("/mcp/")
    assert response.status_code != 307


async def test_the_tool_span_on_the_server_is_a_child_of_the_client_call(spans: InMemorySpanExporter) -> None:
    port = _free_port()
    app = create_app(container=_build_container(port))

    async with (
        _serve(app, port) as base_url,
        httpx.AsyncClient(base_url=base_url, timeout=30.0, headers=AUTH) as client,
    ):
        await client.post("/api/v1/invoke", json={"message": "check the 18:00 table and find Anna"})

    finished = spans.get_finished_spans()
    clients = [span for span in finished if span.name == "mcp.client tools/call"]
    servers = [span for span in finished if span.name.startswith("mcp.server tools/call ")]
    (run,) = [span for span in finished if span.name == "invoke_agent ops-agent"]

    assert len(clients) == len(servers) == 2
    # The context crossed the loopback in `_meta`: each server span's parent is a client call.
    assert sorted(span.parent.span_id for span in servers if span.parent) == sorted(
        span.context.span_id for span in clients
    )
    assert {span.context.trace_id for span in clients + servers} == {run.context.trace_id}
    # And it still links to the POST /mcp request that carried it.
    assert all(len(span.links) == 1 for span in servers)
    assert run.attributes is not None and run.attributes["agent.outcome"] == "answered"
    # The customer's name, a tool argument, is on no span.
    assert not any("Anna" in str(value) for span in finished for value in (span.attributes or {}).values())


class _StallingLLMClient(ScriptedLLMClient):
    """Asks for one tool, then never answers: the run is in flight when the client leaves."""

    async def complete(
        self, messages: Sequence[LLMMessage], *, tools: Sequence[ToolDefinition] | None = None
    ) -> LLMResponse:
        if self.calls:
            await asyncio.sleep(60)
        return await super().complete(messages, tools=tools)


async def test_a_client_that_disconnects_mid_run_is_counted_as_such(metric_value: Callable[..., float]) -> None:
    port = _free_port()
    container = _build_container(port)
    container.__dict__["llm_client"] = _StallingLLMClient(
        [
            LLMResponse(
                content="",
                tool_calls=(ToolCall(id="c2", name="lookup_customer", arguments='{"name_or_id": "Anna"}'),),
            )
        ]
    )
    app = create_app(container=container)
    before = metric_value("agent.runs", outcome="client_disconnect")

    async with (
        _serve(app, port) as base_url,
        httpx.AsyncClient(base_url=base_url, timeout=30.0, headers=AUTH) as client,
    ):
        async with client.stream("POST", "/api/v1/invoke", json={"message": "find Anna"}) as response:
            async for line in response.aiter_lines():
                if line.startswith("event: tool_result"):
                    break  # leave while the model is "thinking" about the result
        for _ in range(100):
            if metric_value("agent.runs", outcome="client_disconnect") > before:
                break
            await asyncio.sleep(0.05)

    assert metric_value("agent.runs", outcome="client_disconnect") - before == 1
