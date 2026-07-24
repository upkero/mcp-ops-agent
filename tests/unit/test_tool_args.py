"""The tool argument models are the validation gate: a bad call is rejected by
Pydantic before any tool/service code runs. These tests pin that contract."""

import pytest
from pydantic import ValidationError

from src.app.mcp.v1.tools.booking import CheckAvailabilityArgs
from src.app.mcp.v1.tools.customers import LookupCustomerArgs
from src.app.mcp.v1.tools.notifications import SendNotificationArgs
from src.app.mcp.v1.tools.pricing import CalculateQuoteArgs


def test_valid_availability_args_parse() -> None:
    args = CheckAvailabilityArgs(date="2026-07-25", time="18:00", resource_type="table")
    assert args.resource_type == "table"
    assert args.date.isoformat() == "2026-07-25"
    assert args.time.strftime("%H:%M") == "18:00"


def test_availability_rejects_unknown_resource_type() -> None:
    with pytest.raises(ValidationError):
        CheckAvailabilityArgs(date="2026-07-25", time="18:00", resource_type="spaceship")


def test_availability_rejects_malformed_date() -> None:
    with pytest.raises(ValidationError):
        CheckAvailabilityArgs(date="not-a-date", time="18:00", resource_type="table")


def test_quote_rejects_zero_quantity() -> None:
    with pytest.raises(ValidationError):
        CalculateQuoteArgs(service="Deep Tissue Massage", quantity=0)


def test_quote_rejects_blank_service() -> None:
    with pytest.raises(ValidationError):
        CalculateQuoteArgs(service="", quantity=1)


def test_lookup_rejects_blank_input() -> None:
    with pytest.raises(ValidationError):
        LookupCustomerArgs(name_or_id="")


def test_notification_rejects_blank_message() -> None:
    with pytest.raises(ValidationError):
        SendNotificationArgs(recipient="Anna", message="")
