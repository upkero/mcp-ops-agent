import json

from src.app.contracts.agent.agent_event import AgentEvent


def format_sse(event: AgentEvent) -> str:
    """Serialise an AgentEvent into a single Server-Sent Events frame.

    Hand-rolled on purpose (KISS): SSE is a trivial text protocol —
    ``event: <type>\\ndata: <json>\\n\\n`` — so it needs no extra dependency.
    ``ensure_ascii=False`` keeps non-Latin text (e.g. Russian) readable in the
    browser stream; ``default=str`` covers Decimals and other non-JSON scalars.
    """
    payload = json.dumps(event.data, ensure_ascii=False, default=str)
    return f"event: {event.type}\ndata: {payload}\n\n"
