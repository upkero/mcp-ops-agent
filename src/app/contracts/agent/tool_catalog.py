from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """A tool advertised by the MCP server (name + description + JSON Schema).

    The orchestrator converts these into the provider's function-calling format;
    keeping them as a framework-free contract means the orchestrator never imports
    the MCP SDK types directly.
    """

    name: str
    description: str
    input_schema: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ToolCallOutcome:
    """The result of one MCP tool invocation, normalised for the LLM.

    ``content`` is the text fed back to the model; ``is_error`` marks a failed
    call so the loop can surface it without crashing.
    """

    content: str
    is_error: bool
