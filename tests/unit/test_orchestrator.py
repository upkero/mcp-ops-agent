from src.app.contracts.agent.tool_catalog import ToolCallOutcome, ToolDefinition
from src.app.contracts.llm.llm_response import LLMResponse
from src.app.contracts.llm.tool_call import ToolCall
from src.app.core.settings.agent import AgentSettings
from src.app.services.orchestrator import OrchestratorService
from tests.doubles import FakeToolGateway, FakeToolSession, ScriptedLLMClient

_TOOLS = [
    ToolDefinition("check_calendar_availability", "check a slot", {"type": "object"}),
    ToolDefinition("lookup_customer", "find a customer", {"type": "object"}),
]


def _orchestrator(
    *,
    responses: list[LLMResponse],
    outcomes: dict[str, ToolCallOutcome],
    max_steps: int = 6,
) -> tuple[OrchestratorService, FakeToolSession]:
    session = FakeToolSession(tools=_TOOLS, outcomes=outcomes)
    orchestrator = OrchestratorService(
        llm_client=ScriptedLLMClient(responses),
        tool_gateway=FakeToolGateway(session),
        settings=AgentSettings(max_steps=max_steps),
    )
    return orchestrator, session


async def test_compound_request_streams_two_tool_calls_then_final() -> None:
    responses = [
        LLMResponse(
            content="",
            tool_calls=(
                ToolCall(
                    id="c1",
                    name="check_calendar_availability",
                    arguments='{"args": {"date": "2026-07-25", "time": "18:00", "resource_type": "table"}}',
                ),
            ),
        ),
        LLMResponse(
            content="",
            tool_calls=(ToolCall(id="c2", name="lookup_customer", arguments='{"args": {"name_or_id": "Anna"}}'),),
        ),
        LLMResponse(content="The 18:00 table is free and I found Anna Petrova."),
    ]
    outcomes = {
        "check_calendar_availability": ToolCallOutcome(content='{"available": true}', is_error=False),
        "lookup_customer": ToolCallOutcome(content='{"count": 1}', is_error=False),
    }
    orchestrator, session = _orchestrator(responses=responses, outcomes=outcomes)

    events = [event async for event in orchestrator.run("check 18:00 table and find Anna")]

    types = [event.type for event in events]
    assert types == ["tool_call", "tool_result", "tool_call", "tool_result", "final"]
    # Two DISTINCT tools were called, in order, over the (fake) session.
    assert [name for name, _ in session.calls] == ["check_calendar_availability", "lookup_customer"]
    assert events[0].data["name"] == "check_calendar_availability"
    assert events[2].data["name"] == "lookup_customer"
    assert events[-1].data["content"] == "The 18:00 table is free and I found Anna Petrova."


async def test_arguments_are_parsed_from_json_before_the_call() -> None:
    responses = [
        LLMResponse(
            content="",
            tool_calls=(ToolCall(id="c1", name="lookup_customer", arguments='{"args": {"name_or_id": "Anna"}}'),),
        ),
        LLMResponse(content="done"),
    ]
    outcomes = {"lookup_customer": ToolCallOutcome(content="{}", is_error=False)}
    orchestrator, session = _orchestrator(responses=responses, outcomes=outcomes)

    [event async for event in orchestrator.run("find Anna")]

    # The raw JSON string became a dict argument for the MCP call.
    assert session.calls[0][1] == {"args": {"name_or_id": "Anna"}}


async def test_step_limit_stops_the_loop_with_an_error_event() -> None:
    # The model keeps asking for tools forever; the loop must stop at max_steps.
    looping = LLMResponse(
        content="",
        tool_calls=(ToolCall(id="c", name="lookup_customer", arguments='{"args": {"name_or_id": "x"}}'),),
    )
    outcomes = {"lookup_customer": ToolCallOutcome(content="{}", is_error=False)}
    orchestrator, _ = _orchestrator(responses=[looping], outcomes=outcomes, max_steps=2)

    events = [event async for event in orchestrator.run("loop forever")]

    assert events[-1].type == "error"
    assert sum(1 for event in events if event.type == "tool_call") == 2
