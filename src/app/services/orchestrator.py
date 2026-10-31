import asyncio
import json
import logging
import time
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from opentelemetry import trace
from opentelemetry.trace import Span

from src.app.contracts.agent.agent_event import AgentEvent
from src.app.contracts.agent.tool_catalog import ToolCallOutcome, ToolDefinition
from src.app.contracts.llm.llm_message import LLMMessage
from src.app.contracts.llm.tool_call import ToolCall
from src.app.core import metrics
from src.app.core.settings.agent import AgentSettings
from src.app.exceptions.agent import AgentStepLimitError, AgentTimeoutError, ToolGatewayUnavailableError
from src.app.exceptions.llm import LLMError
from src.app.interfaces.agent.tool_gateway import ToolGateway, ToolSession
from src.app.interfaces.llm.llm_client import LLMClient
from src.app.prompts import get_prompt

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)

_PROMPT = get_prompt("ops_agent.system")
_NOTIFY_TOOL = "send_notification"

# How a run ended, named by what it raised; anything else is `error`.
_OUTCOMES: tuple[tuple[type[BaseException], str], ...] = (
    (AgentStepLimitError, "max_iterations"),
    (AgentTimeoutError, "timeout"),
    (LLMError, "llm_error"),
    (ToolGatewayUnavailableError, "tool_gateway_unavailable"),
    # The SSE client went away, and `run` cancels the run with it.
    (asyncio.CancelledError, "client_disconnect"),
)
# The tool arguments a span may carry: booking and pricing parameters. Never a name,
# a recipient or a message.
_SPAN_ARGUMENTS = frozenset({"resource_type", "date", "time", "quantity", "service"})


def _today_label(now: datetime) -> str:
    # The weekday is spelled out: a model given only an ISO date cannot reliably say
    # which day "next Monday" is. The zone says which "today" the server means.
    return f"{now.strftime('%A %Y-%m-%d')} ({now.tzname()})"


@dataclass
class _RunState:
    """One run: where its events go, its conversation, what it has spent, and when it must be over."""

    deadline: float
    emit: Callable[[AgentEvent], None]
    messages: list[LLMMessage] = field(default_factory=list)
    steps: int = 0
    notifications: int = 0
    tool_calls: int = 0
    refusals: int = 0
    tokens: Counter[str] = field(default_factory=Counter)
    # The tools the server advertised: the only values the `tool` metric label takes.
    tool_names: frozenset[str] = frozenset()


async def _before_deadline[T](state: _RunState, awaitable: Awaitable[T]) -> T:
    """Await ``awaitable`` but not past the run's deadline (LLM and tool calls alike)."""
    try:
        async with asyncio.timeout_at(state.deadline) as scope:
            return await awaitable
    except TimeoutError as exc:
        if scope.expired():
            raise AgentTimeoutError() from exc
        raise


def _refuse(state: _RunState, reason: str, limit: int, error: str) -> ToolCallOutcome:
    """Answer a call with a refusal, and log and count it under ``reason``."""
    logger.warning("agent.tool_refused", extra={"reason": reason, "limit": limit})
    state.refusals += 1
    metrics.agent_refusals.add(1, {"reason": reason})
    return ToolCallOutcome(content=json.dumps({"status": "refused", "error": error}), is_error=True)


class OrchestratorService:
    """Agentic loop: an LLM that reaches tools through a real MCP client.

    ``run`` is the loop (list tools → think → call tools → repeat → answer) and
    yields an AgentEvent per observable step, so the SSE route can stream the
    agent "thinking" to the browser. Depends only on the
    LLMClient and ToolGateway *interfaces* (Dependency Inversion): a scripted LLM
    stub + fake gateway in unit tests, the real client + Streamable-HTTP gateway
    in production — the same loop either way. Every tool call goes through the MCP
    session, so nothing is executed outside the protocol.

    A run is bounded four ways: steps, a wall-clock deadline, tool calls per step and
    notifications per run. Output length is capped by LLM_MAX_TOKENS, and how the run
    ended, with the tokens it used, is logged, counted and put on its span.
    """

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        tool_gateway: ToolGateway,
        settings: AgentSettings,
    ) -> None:
        self._llm = llm_client
        self._gateway = tool_gateway
        self._settings = settings

    async def run(self, user_message: str) -> AsyncIterator[AgentEvent]:
        # The run is a task of its own that feeds this generator through a queue. When the
        # SSE client disconnects, this generator is cancelled or closed, maybe later and from
        # another task; the `finally` cancels the run, which then ends in its own context:
        # its outcome is `client_disconnect` and its spans close where they were opened.
        events: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        task = asyncio.create_task(self._run(user_message, events.put_nowait))
        task.add_done_callback(lambda _: events.put_nowait(None))
        try:
            while (event := await events.get()) is not None:
                yield event
            await task  # re-raises whatever ended the run
        finally:
            task.cancel()

    async def _run(self, user_message: str, emit: Callable[[AgentEvent], None]) -> None:
        state = _RunState(deadline=asyncio.get_running_loop().time() + self._settings.run_timeout_seconds, emit=emit)
        started = time.perf_counter()
        outcome = "answered"
        with _tracer.start_as_current_span(
            "invoke_agent ops-agent",
            attributes={
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.agent.name": "ops-agent",
                "gen_ai.prompt.id": _PROMPT.id,
            },
        ) as span:
            try:
                await self._loop(user_message, state)
            except BaseException as exc:
                outcome = next((name for kind, name in _OUTCOMES if isinstance(exc, kind)), "error")
                raise
            finally:
                self._finish(span, state, outcome, time.perf_counter() - started)

    async def _loop(self, user_message: str, state: _RunState) -> None:
        # One MCP session per run (reused across every turn below), then closed.
        async with self._gateway.open_session() as session:
            definitions = await _before_deadline(state, session.list_tools())
            state.tool_names = frozenset(tool.name for tool in definitions)
            tools = [self._to_openai_tool(tool) for tool in definitions]
            # NOTE: the conversation is a list that lives for one run and is
            # dropped with it. There is no store, and the MCP server is stateless_http,
            # so a session per run is all there is to keep. The ceiling: the agent has
            # no memory between requests, so a follow-up like "and the day after?"
            # arrives with no idea what was asked first. Deliberate at this scale — the
            # demo is one compound request. The upgrade is the sibling sales-agent's
            # shape: a ConversationRepository port, in-memory now and Postgres later,
            # with this list loaded from it instead of built fresh. Nothing else here
            # changes.
            state.messages += [
                LLMMessage(role="system", content=_PROMPT.render(today=_today_label(datetime.now().astimezone()))),
                LLMMessage(role="user", content=user_message),
            ]

            for step in range(1, self._settings.max_steps + 1):
                state.steps = step
                response = await _before_deadline(state, self._llm.complete(state.messages, tools=tools))
                state.tokens.update(response.usage or {})

                if not response.tool_calls:
                    state.emit(AgentEvent(type="final", data={"content": response.content}))
                    return

                # Record the assistant turn (with its tool calls) before running them.
                state.messages.append(
                    LLMMessage(
                        role="assistant",
                        content=response.content,
                        tool_calls=response.tool_calls,
                    )
                )
                for index, call in enumerate(response.tool_calls):
                    await self._invoke_tool(session, call, state, index=index)

            logger.warning("agent.max_steps", extra={"max_steps": self._settings.max_steps})
            raise AgentStepLimitError()

    @staticmethod
    def _finish(span: Span, state: _RunState, outcome: str, duration: float) -> None:
        """How the run ended, onto its span, the run metrics and one log line."""
        span.set_attributes(
            {
                "agent.outcome": outcome,
                "agent.steps": state.steps,
                "agent.tool_calls": state.tool_calls,
                "agent.refusals": state.refusals,
                "gen_ai.usage.input_tokens": state.tokens["prompt_tokens"],
                "gen_ai.usage.output_tokens": state.tokens["completion_tokens"],
            }
        )
        metrics.agent_runs.add(1, {"outcome": outcome})
        metrics.agent_run_duration.record(duration, {"outcome": outcome})
        if state.steps:
            metrics.agent_iterations.record(state.steps)
        # The prompt id travels with the usage: when a run looks wrong six weeks
        # from now, this says whether the wording had already changed, and what
        # the run cost.
        tokens = {f"tokens_{name}": count for name, count in state.tokens.items()}
        logger.info(
            "agent.run.finished",
            extra={
                "outcome": outcome,
                "steps": state.steps,
                "duration_ms": round(duration * 1000, 1),
                "prompt_id": _PROMPT.id,
                "tool_calls": state.tool_calls,
                "refusals": state.refusals,
                **tokens,
            },
        )

    async def _invoke_tool(self, session: ToolSession, call: ToolCall, state: _RunState, *, index: int) -> None:
        arguments = self._parse_arguments(call.arguments)
        state.emit(AgentEvent(type="tool_call", data={"id": call.id, "name": call.name, "arguments": arguments}))

        outcome = self._refusal(call, state, index=index) or await self._execute(session, call, arguments, state)
        state.emit(
            AgentEvent(
                type="tool_result",
                data={
                    "id": call.id,
                    "name": call.name,
                    "content": outcome.content,
                    "is_error": outcome.is_error,
                },
            )
        )
        # Feed the result back so the model can reason over it on the next turn.
        state.messages.append(LLMMessage(role="tool", content=outcome.content, tool_call_id=call.id))

    def _refusal(self, call: ToolCall, state: _RunState, *, index: int) -> ToolCallOutcome | None:
        # Every call the model asked for still gets an answer (the provider rejects a
        # tool call with no result), but past a budget the answer is a refusal that
        # never reaches the tool — so a prompt-injected "message every customer" or a
        # fan-out of fifty lookups cannot turn into that many real calls.
        limit = self._settings.max_tool_calls_per_step
        if index >= limit:
            return _refuse(
                state,
                "step_tool_limit",
                limit,
                f"at most {limit} tool calls per step; ask for the rest in a later step",
            )
        if call.name == _NOTIFY_TOOL:
            state.notifications += 1
            limit = self._settings.max_notifications_per_run
            if state.notifications > limit:
                return _refuse(state, "notification_limit", limit, f"notification limit of {limit} per request reached")
        return None

    async def _execute(
        self, session: ToolSession, call: ToolCall, arguments: Mapping[str, object], state: _RunState
    ) -> ToolCallOutcome:
        state.tool_calls += 1
        # The model can name any tool; the label only takes the ones the server advertised.
        tool = call.name if call.name in state.tool_names else "unknown"
        with _tracer.start_as_current_span(
            f"execute_tool {tool}",
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": tool,
                "gen_ai.tool.call.id": call.id,
                **{f"tool.argument.{key}": str(value) for key, value in arguments.items() if key in _SPAN_ARGUMENTS},
            },
        ) as span:
            started = time.perf_counter()
            outcome = "error"
            try:
                result = await _before_deadline(state, session.call_tool(call.name, arguments))
                outcome = "error" if result.is_error else "ok"
                return result
            finally:
                span.set_attribute("tool.outcome", outcome)
                metrics.tool_calls.add(1, {"tool": tool, "outcome": outcome, "side": "client"})
                metrics.tool_duration.record(time.perf_counter() - started, {"tool": tool, "side": "client"})

    @staticmethod
    def _parse_arguments(raw: str) -> Mapping[str, object]:
        # The model returns a JSON string; malformed JSON collapses to an empty
        # object so the tool's own validation reports the problem back to the model.
        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _to_openai_tool(tool: ToolDefinition) -> Mapping[str, object]:
        # MCP tool definition -> provider function-calling schema. The MCP
        # JSON Schema is passed through verbatim, so the tool is described exactly
        # once (on the server) and never re-declared here.
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }
