from dataclasses import dataclass, field
from typing import Literal

from src.app.contracts.llm.tool_call import ToolCall

LLMRole = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """One message in an LLM conversation.

    Extends the base chat message with the two shapes tool-calling needs:
    an assistant turn carrying ``tool_calls``, and a ``role="tool"`` turn carrying
    the result of one call (linked back via ``tool_call_id``).
    """

    role: LLMRole
    content: str
    # Set only on assistant turns that request tool calls.
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    # Set only on tool-result turns (role="tool").
    tool_call_id: str | None = None
    name: str | None = None
