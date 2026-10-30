import functools
import time
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.lowlevel.server import request_ctx
from opentelemetry import propagate, trace
from opentelemetry.trace import Link, SpanKind

from src.app.bootstrap.container import ApplicationContainer
from src.app.core import metrics
from src.app.mcp.v1.tools import availability, customers, notifications, pricing

_tracer = trace.get_tracer(__name__)


class _TracedFastMCP(FastMCP):
    """FastMCP whose every tool runs in a span of its own and is counted.

    Applied here, at registration, so the five tools stay plain functions.
    """

    def tool(self, *args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        register = super().tool(*args, **kwargs)
        return lambda fn: register(_traced(fn))


def _traced(fn: Callable[..., Any]) -> Callable[..., Any]:
    name = fn.__name__

    # functools.wraps keeps the signature FastMCP builds the tool's JSON Schema from.
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # The caller's trace context, from the request's `_meta` (the agent's gateway puts it
        # there). The span still links to the POST /mcp request that carried the call. An
        # external MCP client sends no `_meta.traceparent`, and that request is the parent.
        request = request_ctx.get(None)
        carrier = request.meta.model_dump() if request is not None and request.meta is not None else {}
        http_span = trace.get_current_span().get_span_context()
        caller = propagate.extract(carrier) if "traceparent" in carrier else None
        with _tracer.start_as_current_span(
            f"mcp.server tools/call {name}",
            context=caller,
            kind=SpanKind.SERVER,
            links=[Link(http_span)] if caller is not None and http_span.is_valid else None,
            attributes={"mcp.method.name": "tools/call", "gen_ai.tool.name": name},
        ) as span:
            started = time.perf_counter()
            outcome = "error"
            try:
                result = await fn(*args, **kwargs)
                outcome = "ok"
                return result
            finally:
                span.set_attribute("tool.outcome", outcome)
                metrics.tool_calls.add(1, {"tool": name, "outcome": outcome, "side": "server"})
                metrics.tool_duration.record(time.perf_counter() - started, {"tool": name, "side": "server"})

    return wrapper


def build_mcp_server(container: ApplicationContainer) -> FastMCP:
    """Assemble the FastMCP server and register every versioned tool group.

    Mirrors ``api/v1/router.py``: the tools are declared exactly once, here, and
    every consumer (Claude Desktop, the internal orchestrator, the HTTP route)
    reaches them only through this one server over the MCP protocol — there is no
    parallel copy of the tools anywhere.

    ``stateless_http=True`` keeps each request self-contained (simplest for the
    self-loopback client); ``streamable_http_path="/"`` makes the mounted endpoint
    resolve to ``/mcp/`` once mounted at ``/mcp``: a request to plain ``/mcp`` is answered
    with a 307 to it (see ``main.create_app``).
    """
    mcp = _TracedFastMCP("ops-agent", stateless_http=True, streamable_http_path="/")
    availability.register(mcp, container)
    customers.register(mcp, container)
    pricing.register(mcp, container)
    notifications.register(mcp, container)
    return mcp
