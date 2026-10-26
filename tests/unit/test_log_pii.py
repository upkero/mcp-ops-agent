"""Customer data stays out of the log lines that used to carry it (OBSERVABILITY-AUDIT F7)."""

import logging
from collections.abc import Iterator

import httpx
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.app.api.v1.middleware.rate_limit import _masked
from src.app.core.logging import setup_logging
from src.app.core.settings.logging import LoggingSettings
from src.app.core.settings.ops_core import OpsCoreSettings
from src.app.gateways.agent.mcp_tool_gateway import _McpToolSession
from src.app.gateways.notifications.simulated_channel import SimulatedNotificationChannel
from src.app.gateways.ops_core.client import create_ops_core_http_client
from src.app.gateways.ops_core.customer_gateway import OpsCoreCustomerGateway


def _logged(caplog: pytest.LogCaptureFixture) -> str:
    return " ".join(str(record.__dict__) for record in caplog.records)


async def test_a_simulated_notification_logs_neither_the_recipient_nor_the_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        await SimulatedNotificationChannel().send(recipient="Anna Petrova", message="Your table is ready")

    assert "Anna" not in _logged(caplog)
    assert "table" not in _logged(caplog)


def test_a_rejected_tool_call_logs_the_kind_not_the_arguments(caplog: pytest.LogCaptureFixture) -> None:
    raw = "1 validation error for lookup_customerArguments\nname_or_id\n  input_value='Anna Petrova'"

    with caplog.at_level(logging.WARNING):
        _McpToolSession._safe_error("lookup_customer", raw)

    (record,) = caplog.records
    assert record.error == "invalid_arguments"  # type: ignore[attr-defined]
    assert "Anna" not in _logged(caplog)


def test_the_rate_limit_log_masks_the_address_to_its_network() -> None:
    assert _masked("203.0.113.57") == "203.0.113.0/24"
    assert _masked("2001:db8:1234:5678::1") == "2001:db8:1234::/48"
    assert _masked("unknown") == "unknown"


@pytest.fixture
def configured_logging(caplog: pytest.LogCaptureFixture) -> Iterator[None]:
    """Run the real `setup_logging`, then hand the loggers back as they were."""
    root, httpx_logger = logging.getLogger(), logging.getLogger("httpx")
    saved = (root.handlers[:], root.level, httpx_logger.level)
    setup_logging(LoggingSettings(level="INFO", format="json"))
    root.addHandler(caplog.handler)  # setup_logging replaced the handlers caplog listens on
    yield
    root.handlers, root.level, httpx_logger.level = saved[0], saved[1], saved[2]


@pytest.mark.usefixtures("configured_logging")
async def test_a_customer_search_leaves_no_name_in_any_log_record_or_span(
    caplog: pytest.LogCaptureFixture, spans: InMemorySpanExporter
) -> None:
    """Sanity audit M1: the httpx request line and the span's `url.full` both carried `?search=<name>`."""
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"items": []}))
    client = create_ops_core_http_client(OpsCoreSettings(api_key="test-ops-core-key-1234567890"), transport=transport)

    with caplog.at_level(logging.INFO):
        async with client:
            await OpsCoreCustomerGateway(client=client, max_attempts=1).search("Anna Petrova")

    span_attributes = [dict(span.attributes or {}) for span in spans.get_finished_spans()]
    # The call was made and traced: the path survives, only the query is gone.
    assert [attrs["url.full"] for attrs in span_attributes if "url.full" in attrs] == [
        "http://localhost:8000/api/v1/customers"
    ]
    for leaked in ("Anna", "Petrova"):
        assert leaked not in _logged(caplog)
        assert leaked not in str(span_attributes)
