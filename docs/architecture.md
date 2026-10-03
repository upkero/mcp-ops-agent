# Architecture — MCP Ops Agent

This service follows the shared portfolio architecture — layered, with a strict inward
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
JSON-safe payload. The five tools are declared exactly once, in `mcp/v1/tools/`, and
registered on a single FastMCP instance by `mcp/v1/server.py`.

## One server, mounted once

`main.create_app()` builds the DI container, builds the FastMCP server from it
(`build_mcp_server(container)`), and mounts its Streamable HTTP ASGI app at `/mcp`. The
MCP session manager is run inside the FastAPI lifespan (mounted sub-apps do not receive
Starlette lifespan events, so this is required). `stateless_http=True` keeps each request
self-contained; `streamable_http_path="/"` makes the mounted endpoint resolve to
`/mcp/` (a request to `/mcp` is redirected with a 307).

## The two consumers and the "no bypass" guarantee

- **External clients** (Claude Desktop, MCP Inspector) connect to `/mcp` directly.
- **The internal orchestrator** (`services/orchestrator.py`) depends on two interfaces —
  `LLMClient` and `ToolGateway`. Its concrete gateway
  (`gateways/agent/mcp_tool_gateway.py`) is an **Adapter** over the official MCP
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
     `tool_result`, append the result as a `tool` message; continue. Calls past
     `AGENT_MAX_TOOL_CALLS_PER_STEP`, and `send_notification` calls past
     `AGENT_MAX_NOTIFICATIONS_PER_RUN`, are answered with a refusal and never reach the tool.
3. Step limit reached → `AgentStepLimitError`; the whole run past `AGENT_RUN_TIMEOUT_SECONDS`
   → `AgentTimeoutError`. Either way the route turns it into the terminal `error` event.

The run's token usage (summed over steps) is logged once as `agent.usage`, whatever way the
run ended.

The `api/v1/routers/invoke.py` SSE route only forwards the message and serialises each
yielded event as an SSE frame (`core/sse.py`). It knows nothing about the tools.

## No database

Unlike the sibling services, this one has no `models/` or `db/`. That is also why its
adapters live in `gateways/` rather than `repositories/`: the rule across the portfolio is
`repositories/` for a store this service owns and `gateways/` for somebody else's service
over the network, and everything here is the latter. Every piece of data is fetched from
`ops-core-api` through the `interfaces/ops_core/*` ports — named `*Gateway` for the same
reason — whose httpx adapters share a single client built by `gateways/ops_core/client.py`.
The ports are still shaped like data access on purpose, so `services/` cannot tell an HTTP
call apart from a database read. The `send_notification` tool has no upstream endpoint and
is a deliberate simulation (`gateways/notifications/simulated_channel.py`, a
`NotificationChannel` **Strategy**).

## Errors

Typed exceptions inherit `BaseAppException` (`status_code` / `error_code` / `detail`). The
shared `ops_core_get` helper retries transport errors, 5xx, and 429/503 (honouring
`Retry-After`), maps a surviving 404 to `OpsCoreNotFoundError` and any other error
response to `OpsCoreUnavailableError` (502). Because the SSE response has already started
when the loop runs, failures during a run are delivered as a terminal `error` **event**,
not an HTTP error status. There is one shape, `{"detail", "error_code"}`, for every cause
(step limit, timeout, LLM failure, anything unexpected as `internal_server_error`). A tool
that fails is not a run failure: the model gets a `tool_result` with `is_error` and a short
fixed text (`invalid_arguments` / `tool_failed`) — FastMCP's own message, which carries
library names and upstream status lines, is logged and not forwarded.

## Operational surface

- `GET /health/live` — the process is up. Checks nothing else, so a container is never
  killed because OpenAI is having a bad morning. This is what Docker's `HEALTHCHECK` polls.
- `GET /health/ready` — pings both upstreams (LLM + ops-core-api via
  `OpsCoreHealthChecker`) and returns `{"status":"ok"}`, or 503 with
  `{"detail":"dependencies unavailable: llm", ...}` naming the failing dependency.
- `POST /api/v1/invoke` is gated by an optional `X-API-Key` (`SECURITY_API_KEY`): open
  when unset (demo friendly), required when set. It is also the one path behind a per-IP
  rate limit (`api/v1/middleware/rate_limit.py`), because one call to it can drive up to
  `AGENT_MAX_STEPS` LLM calls — the cap bounds spend, not just abuse.
- `/mcp` is left to the MCP protocol's own auth story and stays open here, so the
  self-loopback needs no key. On a real deployment that is a perimeter decision rather
  than a code one: close `/mcp` at the edge and expose only `/api/v1/invoke`.
