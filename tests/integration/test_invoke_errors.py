"""Every failure of a run reaches the browser as one `event: error` frame: {detail, error_code}."""

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from src.app.bootstrap.container import ApplicationContainer
from src.app.contracts.agent.agent_event import AgentEvent
from src.app.exceptions.agent import AgentStepLimitError, AgentTimeoutError
from src.app.exceptions.llm import LLMGenerationError
from src.app.gateways.agent.mcp_tool_gateway import _McpToolSession
from src.app.mcp.v1.server import build_mcp_server
from src.main import create_app
from tests.conftest import AUTH


class _FailingOrchestrator:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def run(self, user_message: str) -> AsyncIterator[AgentEvent]:
        yield AgentEvent(type="tool_call", data={"id": "1", "name": "x", "arguments": {}})
        raise self._error


async def _error_frame(error: Exception) -> tuple[str, dict[str, object]]:
    container = ApplicationContainer()
    container.__dict__["orchestrator"] = _FailingOrchestrator(error)
    transport = httpx.ASGITransport(app=create_app(container=container))
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=AUTH) as client:
        response = await client.post("/api/v1/invoke", json={"message": "hi"})
    assert response.status_code == 200
    last = response.text.strip().split("\n\n")[-1]
    event, data = last.split("\n")
    return event, json.loads(data.removeprefix("data: "))


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (AgentStepLimitError(), "agent_step_limit"),
        (AgentTimeoutError(), "agent_timeout"),
        (LLMGenerationError("LLM provider request failed."), "llm_generation_error"),
        (RuntimeError("boom"), "internal_server_error"),
    ],
)
async def test_every_run_failure_is_an_error_event_with_detail_and_code(error: Exception, code: str) -> None:
    event, data = await _error_frame(error)

    assert event == "event: error"
    assert set(data) == {"detail", "error_code"}
    assert data["error_code"] == code
    assert data["detail"]


async def test_a_failed_tool_reaches_the_model_and_the_browser_without_library_text() -> None:
    server = build_mcp_server(ApplicationContainer())

    async with create_connected_server_and_client_session(server._mcp_server) as session:
        outcome = await _McpToolSession(session).call_tool(
            "calculate_quote", {"service": "Deep Tissue Massage", "quantity": 1_000_000}
        )

    assert outcome.is_error is True
    assert json.loads(outcome.content)["error"] == "invalid_arguments"
    assert "pydantic" not in outcome.content
    assert "validation error" not in outcome.content
