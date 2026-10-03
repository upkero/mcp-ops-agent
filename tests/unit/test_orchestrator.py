import logging
from datetime import datetime

import pytest

from src.app.contracts.agent.agent_event import AgentEvent
from src.app.contracts.agent.tool_catalog import ToolCallOutcome, ToolDefinition
from src.app.contracts.llm.llm_response import LLMResponse
from src.app.contracts.llm.tool_call import ToolCall
from src.app.core.settings.agent import AgentSettings
from src.app.exceptions.agent import AgentStepLimitError, AgentTimeoutError
from src.app.services.orchestrator import OrchestratorService
from tests.fakes import FakeToolGateway, FakeToolSession, ScriptedLLMClient, SlowToolSession

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
                    arguments='{"date": "2026-07-25", "time": "18:00", "resource_type": "table"}',
                ),
            ),
        ),
        LLMResponse(
            content="",
            tool_calls=(ToolCall(id="c2", name="lookup_customer", arguments='{"name_or_id": "Anna"}'),),
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
            tool_calls=(ToolCall(id="c1", name="lookup_customer", arguments='{"name_or_id": "Anna"}'),),
        ),
        LLMResponse(content="done"),
    ]
    outcomes = {"lookup_customer": ToolCallOutcome(content="{}", is_error=False)}
    orchestrator, session = _orchestrator(responses=responses, outcomes=outcomes)

    [event async for event in orchestrator.run("find Anna")]

    # The raw JSON string became a dict argument for the MCP call.
    assert session.calls[0][1] == {"name_or_id": "Anna"}


async def test_step_limit_stops_the_loop_with_a_typed_error() -> None:
    # The model keeps asking for tools forever; the loop must stop at max_steps.
    looping = LLMResponse(
        content="",
        tool_calls=(ToolCall(id="c", name="lookup_customer", arguments='{"name_or_id": "x"}'),),
    )
    outcomes = {"lookup_customer": ToolCallOutcome(content="{}", is_error=False)}
    orchestrator, _ = _orchestrator(responses=[looping], outcomes=outcomes, max_steps=2)

    events: list[AgentEvent] = []
    with pytest.raises(AgentStepLimitError):
        async for event in orchestrator.run("loop forever"):
            events.append(event)

    assert sum(1 for event in events if event.type == "tool_call") == 2


async def test_the_run_tells_the_model_what_day_it_is() -> None:
    llm = ScriptedLLMClient([LLMResponse(content="ok")])
    orchestrator = OrchestratorService(
        llm_client=llm,
        tool_gateway=FakeToolGateway(FakeToolSession(tools=_TOOLS, outcomes={})),
        settings=AgentSettings(),
    )

    [event async for event in orchestrator.run("is a table free next Monday?")]

    system_prompt = llm.calls[0][0][0].content
    assert datetime.now().strftime("%A %Y-%m-%d") in system_prompt


async def test_notifications_past_the_per_run_budget_are_refused_without_calling_the_tool() -> None:
    notify = ToolCall(id="n", name="send_notification", arguments='{"recipient": "Anna", "message": "hi"}')
    responses = [
        LLMResponse(content="", tool_calls=(notify, notify, notify)),
        LLMResponse(content="done"),
    ]
    session = FakeToolSession(
        tools=_TOOLS,
        outcomes={"send_notification": ToolCallOutcome(content='{"status": "simulated"}', is_error=False)},
    )
    orchestrator = OrchestratorService(
        llm_client=ScriptedLLMClient(responses),
        tool_gateway=FakeToolGateway(session),
        settings=AgentSettings(max_notifications_per_run=2),
    )

    events = [event async for event in orchestrator.run("notify everyone")]

    assert len(session.calls) == 2
    results = [event.data for event in events if event.type == "tool_result"]
    assert [result["is_error"] for result in results] == [False, False, True]
    assert "limit of 2" in str(results[2]["content"])


def _lookup(call_id: str) -> ToolCall:
    return ToolCall(id=call_id, name="lookup_customer", arguments='{"name_or_id": "x"}')


async def test_a_run_that_outlives_its_deadline_is_stopped() -> None:
    responses = [LLMResponse(content="", tool_calls=(_lookup("c1"),)), LLMResponse(content="done")]
    session = SlowToolSession(
        delay=1.0,
        tools=_TOOLS,
        outcomes={"lookup_customer": ToolCallOutcome(content="{}", is_error=False)},
    )
    orchestrator = OrchestratorService(
        llm_client=ScriptedLLMClient(responses),
        tool_gateway=FakeToolGateway(session),
        settings=AgentSettings(run_timeout_seconds=0.05),
    )

    seen: list[str] = []
    with pytest.raises(AgentTimeoutError):
        async for event in orchestrator.run("slow"):
            seen.append(event.type)

    assert seen == ["tool_call"]  # the slow call started, its result never came


async def test_tool_calls_past_the_per_step_cap_are_refused_but_still_answered() -> None:
    responses = [
        LLMResponse(content="", tool_calls=tuple(_lookup(f"c{i}") for i in range(5))),
        LLMResponse(content="done"),
    ]
    llm = ScriptedLLMClient(responses)
    session = FakeToolSession(
        tools=_TOOLS,
        outcomes={"lookup_customer": ToolCallOutcome(content="{}", is_error=False)},
    )
    orchestrator = OrchestratorService(
        llm_client=llm,
        tool_gateway=FakeToolGateway(session),
        settings=AgentSettings(max_tool_calls_per_step=2),
    )

    events = [event async for event in orchestrator.run("fan out")]

    assert len(session.calls) == 2
    results = [event.data["is_error"] for event in events if event.type == "tool_result"]
    assert results == [False, False, True, True, True]
    # The model got an answer for every call it made (providers reject a dangling one).
    second_turn = llm.calls[1][0]
    assert sum(1 for message in second_turn if message.role == "tool") == 5


async def test_token_usage_is_summed_across_steps_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    responses = [
        LLMResponse(content="", tool_calls=(_lookup("c1"),), usage={"prompt_tokens": 100, "completion_tokens": 10}),
        LLMResponse(content="done", usage={"prompt_tokens": 150, "completion_tokens": 20}),
    ]
    orchestrator, _ = _orchestrator(
        responses=responses,
        outcomes={"lookup_customer": ToolCallOutcome(content="{}", is_error=False)},
    )

    with caplog.at_level(logging.INFO, logger="src.app.services.orchestrator"):
        [event async for event in orchestrator.run("count tokens")]

    record = next(r for r in caplog.records if r.message == "agent.usage")
    assert (record.steps, record.tokens_prompt_tokens, record.tokens_completion_tokens) == (2, 250, 30)  # type: ignore[attr-defined]
