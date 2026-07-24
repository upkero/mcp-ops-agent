import json
import logging
from collections.abc import AsyncIterator, Mapping

from src.app.contracts.agent.agent_event import AgentEvent
from src.app.contracts.agent.tool_catalog import ToolDefinition
from src.app.contracts.llm.llm_message import LLMMessage
from src.app.contracts.llm.tool_call import ToolCall
from src.app.core.settings.agent import AgentSettings
from src.app.interfaces.agent.tool_gateway import ToolGateway, ToolSession
from src.app.interfaces.llm.llm_client import LLMClient
from src.app.llm.skills import OPS_AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class OrchestratorService:
    """Agentic loop: an LLM that reaches tools through a real MCP client.

    Template Method — ``run`` fixes the loop skeleton (list tools → think → call
    tools → repeat → answer) and yields an AgentEvent per observable step, so the
    SSE route can stream the agent "thinking" to the browser. Depends only on the
    LLMClient and ToolGateway *interfaces* (Dependency Inversion): a scripted LLM
    stub + fake gateway in unit tests, the real client + Streamable-HTTP gateway
    in production — the same loop either way. Every tool call goes through the MCP
    session, so nothing is executed outside the protocol.
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
        # One MCP session per run (reused across every turn below), then closed.
        async with self._gateway.open_session() as session:
            tools = [self._to_openai_tool(tool) for tool in await session.list_tools()]
            messages: list[LLMMessage] = [
                LLMMessage(role="system", content=OPS_AGENT_SYSTEM_PROMPT),
                LLMMessage(role="user", content=user_message),
            ]

            for step in range(self._settings.max_steps):
                response = await self._llm.complete(messages, tools=tools)

                if not response.tool_calls:
                    logger.info("agent.final", extra={"steps": step + 1})
                    yield AgentEvent(type="final", data={"content": response.content})
                    return

                # Record the assistant turn (with its tool calls) before running them.
                messages.append(
                    LLMMessage(
                        role="assistant",
                        content=response.content,
                        tool_calls=response.tool_calls,
                    )
                )
                for call in response.tool_calls:
                    async for event in self._invoke_tool(session, messages, call):
                        yield event

            logger.warning("agent.max_steps", extra={"max_steps": self._settings.max_steps})
            yield AgentEvent(
                type="error",
                data={"message": "Reached the step limit without a final answer."},
            )

    async def _invoke_tool(
        self,
        session: ToolSession,
        messages: list[LLMMessage],
        call: ToolCall,
    ) -> AsyncIterator[AgentEvent]:
        arguments = self._parse_arguments(call.arguments)
        yield AgentEvent(
            type="tool_call",
            data={"id": call.id, "name": call.name, "arguments": arguments},
        )

        outcome = await session.call_tool(call.name, arguments)
        yield AgentEvent(
            type="tool_result",
            data={
                "id": call.id,
                "name": call.name,
                "content": outcome.content,
                "is_error": outcome.is_error,
            },
        )
        # Feed the result back so the model can reason over it on the next turn.
        messages.append(
            LLMMessage(role="tool", content=outcome.content, tool_call_id=call.id, name=call.name)
        )

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
        # Bridge: MCP tool definition -> provider function-calling schema. The MCP
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
