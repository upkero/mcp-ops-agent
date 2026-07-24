from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A tool invocation requested by the model.

    ``arguments`` is the raw JSON string exactly as the provider returned it —
    parsed by the orchestrator, never here, so this contract stays transport- and
    framework-free.
    """

    id: str
    name: str
    arguments: str
