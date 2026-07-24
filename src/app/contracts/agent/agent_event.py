from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

AgentEventType = Literal["tool_call", "tool_result", "final", "error"]


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """One observable step of the agentic loop, streamed to the browser as SSE.

    Deliberately generic (a tagged ``type`` + a ``data`` mapping) so new event
    kinds never change the transport: the SSE router just serialises whatever the
    orchestrator yields.
    """

    type: AgentEventType
    data: Mapping[str, object]
