"""Customer data stays out of the log lines that used to carry it (OBSERVABILITY-AUDIT F7)."""

import logging

import pytest

from src.app.api.v1.middleware.rate_limit import _masked
from src.app.gateways.agent.mcp_tool_gateway import _McpToolSession
from src.app.gateways.notifications.simulated_channel import SimulatedNotificationChannel


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
