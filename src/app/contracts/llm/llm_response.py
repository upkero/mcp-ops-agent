from collections.abc import Mapping
from dataclasses import dataclass, field

from src.app.contracts.llm.tool_call import ToolCall


@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str
    model: str | None = None
    finish_reason: str | None = None
    usage: Mapping[str, int] | None = None
    metadata: Mapping[str, object] | None = None
    # Non-empty when the model chose to call one or more tools this turn.
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
