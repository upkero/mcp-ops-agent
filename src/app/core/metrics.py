"""Metric instruments, defined once.

A label is a bounded set (an outcome, a tool the server advertises, a model), never
a prompt, an id or an exception message, so the number of series stays fixed. The
instruments are created at import against the global meter, which binds to the real
provider as soon as `core.telemetry.setup_metrics` installs it.
"""

from opentelemetry import metrics

_meter = metrics.get_meter("mcp-ops-agent")

agent_runs = _meter.create_counter("agent.runs", description="Agent runs, by how they ended.")
agent_run_duration = _meter.create_histogram(
    "agent.run.duration",
    unit="s",
    description="Wall-clock time of one agent run; the SSE request's own duration says nothing.",
    explicit_bucket_boundaries_advisory=[0.5, 1, 2, 4, 8, 15, 30, 45, 60, 90],
)
agent_iterations = _meter.create_histogram(
    "agent.iterations",
    description="LLM steps one run took.",
    explicit_bucket_boundaries_advisory=[1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 25],
)
agent_refusals = _meter.create_counter(
    "agent.refusals", description="Tool calls the agent refused before they reached a tool, by guardrail."
)
tool_calls = _meter.create_counter(
    "mcp.tool.calls", description="MCP tool calls, by tool, outcome and side (client or server)."
)
tool_duration = _meter.create_histogram(
    "mcp.tool.duration",
    unit="s",
    description="MCP tool call duration, by tool and side.",
    explicit_bucket_boundaries_advisory=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
)
operation_duration = _meter.create_histogram(
    "gen_ai.client.operation.duration",
    unit="s",
    description="LLM request duration.",
    explicit_bucket_boundaries_advisory=[
        0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92,
    ],
)
token_usage = _meter.create_histogram(
    "gen_ai.client.token.usage",
    unit="{token}",
    description="Tokens per LLM request.",
    explicit_bucket_boundaries_advisory=[1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144],
)
llm_cost = _meter.create_counter(
    "llm.cost", description="LLM spend in USD, as reported by the provider (OpenRouter usage.cost)."
)
finish_reasons = _meter.create_counter(
    "llm.finish_reasons", description="LLM replies by finish reason; `length` means truncation."
)
