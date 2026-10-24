import os

# Set before importing anything from src: settings are read at import time and
# then cached. These are throwaway values so importing the container never fails
# on a required field; the tests inject fakes for the things that matter.
os.environ.setdefault("OPS_CORE_API_KEY", "test-ops-core-key-1234567890")
TEST_API_KEY = "test-inbound-key-1234567890"
os.environ.setdefault("SECURITY_API_KEY", TEST_API_KEY)
AUTH = {"X-API-Key": TEST_API_KEY}
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("LLM_MODEL", "stub-model")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("LOG_LEVEL", "WARNING")
# A small cap so the rate-limit test is cheap; well above what any other test sends.
os.environ.setdefault("INVOKE_RATE_LIMIT_PER_MINUTE", "5")

from collections.abc import Callable, Iterator  # noqa: E402

import pytest  # noqa: E402
from opentelemetry import metrics  # noqa: E402
from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from opentelemetry.sdk.metrics.export import InMemoryMetricReader  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

from src.app.api.v1.middleware.rate_limit import reset_rate_limit  # noqa: E402
from src.app.core.settings.agent import AgentSettings  # noqa: E402
from src.app.core.settings.app import AppSettings  # noqa: E402
from src.app.core.settings.llm import LLMSettings  # noqa: E402
from src.app.core.settings.logging import LoggingSettings  # noqa: E402
from src.app.core.settings.ops_core import OpsCoreSettings  # noqa: E402
from src.app.core.settings.security import SecuritySettings  # noqa: E402
from src.app.core.telemetry import setup_tracing  # noqa: E402

# A developer's local .env must not change what the tests see (a SECURITY_API_KEY in
# it turns every invoke test into a 401). Environment variables set above still apply.
for _settings in (AgentSettings, AppSettings, LLMSettings, LoggingSettings, OpsCoreSettings, SecuritySettings):
    _settings.model_config["env_file"] = None

# Installed at import, before any test module imports `src.main` (which builds the app and
# would install a provider with no reader): OTel refuses to replace a global provider.
_metric_reader = InMemoryMetricReader()
metrics.set_meter_provider(MeterProvider(metric_readers=[_metric_reader]))
_span_exporter = InMemorySpanExporter()


@pytest.fixture
def spans() -> Iterator[InMemorySpanExporter]:
    provider = setup_tracing("mcp-ops-agent", "mcp-ops-agent")
    assert isinstance(provider, TracerProvider)
    if not getattr(provider, "_test_exporter_added", False):
        provider.add_span_processor(SimpleSpanProcessor(_span_exporter))
        provider._test_exporter_added = True  # type: ignore[attr-defined]
    _span_exporter.clear()
    yield _span_exporter
    _span_exporter.clear()


@pytest.fixture
def metric_value() -> Callable[..., float]:
    """The running total of a counter, or the sample count of a histogram, for the data
    points whose attributes include `attrs`. Totals are cumulative across the whole test
    run, so a test compares a value before and after, never against zero."""

    def read(name: str, **attrs: object) -> float:
        total = 0.0
        data = _metric_reader.get_metrics_data()
        for resource_metrics in data.resource_metrics if data else ():
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    if metric.name != name:
                        continue
                    for point in metric.data.data_points:
                        point_attrs = point.attributes or {}
                        if all(point_attrs.get(key) == value for key, value in attrs.items()):
                            total += getattr(point, "value", None) or getattr(point, "count", 0) or 0
        return total

    return read


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> Iterator[None]:
    """The limiter's counters are process-global; keep cases independent."""
    reset_rate_limit()
    yield
    reset_rate_limit()
