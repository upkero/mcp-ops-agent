from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from src.app.contracts.llm.llm_message import LLMMessage
from src.app.contracts.llm.llm_response import LLMResponse


class LLMClient(ABC):
    """Abstraction over a chat-completion LLM with optional tool-calling.

    ``tools`` (when given) are provider-format function schemas; the returned
    LLMResponse carries ``tool_calls`` when the model chooses to use one. Services
    depend on this interface, never on the concrete SDK client.
    """

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    async def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> LLMResponse: ...

    @abstractmethod
    async def ping(self) -> bool: ...

    @abstractmethod
    async def close(self) -> None: ...
