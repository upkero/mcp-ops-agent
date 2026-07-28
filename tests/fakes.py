"""Reusable fakes (not collected — no ``test_`` prefix).

Kept Liskov-safe: each double implements the real interface, so it can stand in
for the production object anywhere the interface is expected.
"""

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager

from src.app.contracts.agent.tool_catalog import ToolCallOutcome, ToolDefinition
from src.app.contracts.llm.llm_message import LLMMessage
from src.app.contracts.llm.llm_response import LLMResponse
from src.app.interfaces.agent.tool_gateway import ToolGateway, ToolSession
from src.app.interfaces.llm.llm_client import LLMClient


class ScriptedLLMClient(LLMClient):
    """LLMClient stub that returns a fixed queue of responses, in order.

    Once the queue is exhausted it keeps returning the last response, so a loop
    that never terminates can still be driven to its step limit deterministically.
    """

    def __init__(self, responses: Sequence[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[list[LLMMessage], object]] = []

    @property
    def model_name(self) -> str:
        return "scripted"

    @property
    def provider_name(self) -> str:
        return "scripted"

    async def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> LLMResponse:
        self.calls.append((list(messages), tools))
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class FakeToolSession(ToolSession):
    """In-process ToolSession that records calls and returns canned outcomes."""

    def __init__(
        self,
        *,
        tools: Sequence[ToolDefinition],
        outcomes: Mapping[str, ToolCallOutcome],
    ) -> None:
        self._tools = list(tools)
        self._outcomes = dict(outcomes)
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def list_tools(self) -> Sequence[ToolDefinition]:
        return self._tools

    async def call_tool(self, name: str, arguments: Mapping[str, object]) -> ToolCallOutcome:
        self.calls.append((name, dict(arguments)))
        return self._outcomes[name]


class FakeToolGateway(ToolGateway):
    """ToolGateway that hands out one pre-built FakeToolSession."""

    def __init__(self, session: FakeToolSession) -> None:
        self._session = session

    @asynccontextmanager
    async def open_session(self) -> AsyncIterator[ToolSession]:
        yield self._session
