# Architecture — MCP Ops Agent

This service follows the shared portfolio architecture in
[`../../architecture.md`](../../architecture.md) — layered, with a strict inward
dependency rule (outer layers depend on inner, never the reverse). This document covers
only what is specific to the MCP agent.

## The `mcp/v1/` layer

Alongside `api/v1/` there is a versioned MCP layer that mirrors it one-for-one:

| HTTP world | MCP world | Role |
|------------|-----------|------|
| `api/v1/routers/*` | `mcp/v1/tools/*` | One file per feature; adapts a request to a service call. |
| `api/v1/router.py` | `mcp/v1/server.py` | Aggregates the feature units into one server/router. |

The dependency rule is identical to `api/v1/`: **`mcp/v1/tools/` calls `services/` and
never contains business logic** — a tool only validates its arguments (a Pydantic model,
from which FastMCP derives the JSON Schema) and shapes the service result into a
JSON-safe payload. The four tools are declared exactly once, in `mcp/v1/tools/`, and
registered on a single FastMCP instance by `mcp/v1/server.py`.

## One server, mounted once

`main.create_app()` builds the DI container, builds the FastMCP server from it
(`build_mcp_server(container)`), and mounts its Streamable HTTP ASGI app at `/mcp`. The
MCP session manager is run inside the FastAPI lifespan (mounted sub-apps do not receive
Starlette lifespan events, so this is required). `stateless_http=True` keeps each request
self-contained; `streamable_http_path="/"` makes the mounted endpoint resolve to exactly
`/mcp`.

## The two consumers and the "no bypass" guarantee

- **External clients** (Claude Desktop, MCP Inspector) connect to `/mcp` directly.
- **The internal orchestrator** (`services/orchestrator.py`) depends on two interfaces —
  `LLMClient` and `ToolGateway`. Its concrete gateway
  (`repositories/agent/mcp_tool_gateway.py`) is an **Adapter** over the official MCP
  client that connects to the server's *own* `/mcp` over Streamable HTTP
  (`AGENT_MCP_SELF_URL`). So even the internal agent reaches tools only through genuine
  MCP JSON-RPC — there is no in-process shortcut to the tools or services.

The orchestrator opens **one MCP session per run** (reused across the run's turns, closed
after), which pairs with the stateless server. A per-run `initialize` handshake is one
loopback round trip — negligible next to LLM latency — and avoids any shared-session
concurrency or reconnect logic. (A session cannot be opened once at startup for a
self-loopback: uvicorn finishes lifespan startup before it accepts connections.)

## The agentic loop (Template Method)

`OrchestratorService.run(message)` fixes the skeleton and yields an `AgentEvent` per
observable step:

1. Open one MCP session; `list_tools()` → convert each to the provider's function-calling
   schema (the MCP JSON Schema is passed through verbatim — the tool is described once).
2. Loop up to `AGENT_MAX_STEPS`: `llm.complete(messages, tools=…)`.
   - No tool calls → emit `final`, stop.
   - Tool calls → for each: emit `tool_call`, run it over the session, emit
     `tool_result`, append the result as a `tool` message; continue.
3. Step limit reached → emit `error`.

The `api/v1/routers/mcp_tools.py` SSE route only forwards the message and serialises each
yielded event as an SSE frame (`core/sse.py`). It knows nothing about the tools.

## No database

Unlike the sibling services, this one has no `models/` or `db/`. Every piece of data is
fetched from `ops-core-api` through the `interfaces/ops_core/*` repositories, whose httpx
adapters share a single client built by `repositories/ops_core/client.py`. The
`send_notification` tool has no upstream endpoint and is a deliberate simulation
(`repositories/notifications/simulated_channel.py`, a `NotificationChannel` **Strategy**).

## Errors

Typed exceptions inherit `BaseAppException` (`status_code` / `error_code` / `detail`). The
ops-core adapters map transport/5xx failures to `OpsCoreUnavailableError` (502) and a 404
to `OpsCoreNotFoundError`. Because the SSE response has already started when the loop
runs, failures during a run are delivered as a terminal `error` **event**, not an HTTP
error status.
