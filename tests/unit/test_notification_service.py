from unittest.mock import AsyncMock

import pytest

from src.app.contracts.notifications.receipt import NotificationReceipt
from src.app.contracts.ops_core.customer import Customer
from src.app.exceptions.notification import NotificationRecipientError
from src.app.gateways.notifications.simulated_channel import SimulatedNotificationChannel
from src.app.interfaces.notifications.channel import NotificationChannel
from src.app.interfaces.ops_core.customers import CustomerGateway
from src.app.services.customer import CustomerService
from src.app.services.notification import NotificationService

_ANNA = Customer("11111111-1111-1111-1111-111111111111", "Anna Petrova", "active", None, None)
_ANNA_K = Customer("22222222-2222-2222-2222-222222222222", "Anna Kowalski", "active", None, None)


def _service(found: list[Customer]) -> tuple[NotificationService, AsyncMock]:
    channel = AsyncMock(spec=NotificationChannel)
    channel.send.return_value = NotificationReceipt("simulated", "x", "hi")
    gateway = AsyncMock(spec=CustomerGateway)
    gateway.search.return_value = found
    gateway.get_by_id.return_value = found[0] if found else None
    return NotificationService(channel=channel, customers=CustomerService(customers=gateway)), channel


async def test_send_delivers_to_the_resolved_customer() -> None:
    service, channel = _service([_ANNA])

    receipt = await service.send(recipient="Anna", message="hi")

    channel.send.assert_awaited_once_with(recipient="Anna Petrova", message="hi")
    assert receipt.status == "simulated"


async def test_a_customer_id_is_a_valid_recipient() -> None:
    service, channel = _service([_ANNA])

    await service.send(recipient=_ANNA.id, message="hi")

    channel.send.assert_awaited_once_with(recipient="Anna Petrova", message="hi")


@pytest.mark.parametrize("recipient", ["ops@example.com", "+1-555-0199", "nobody"])
async def test_a_recipient_who_is_not_a_customer_is_rejected(recipient: str) -> None:
    service, channel = _service([])

    with pytest.raises(NotificationRecipientError):
        await service.send(recipient=recipient, message="Your account is locked")

    channel.send.assert_not_awaited()


async def test_an_ambiguous_name_is_rejected_but_the_full_name_is_not() -> None:
    service, channel = _service([_ANNA, _ANNA_K])

    with pytest.raises(NotificationRecipientError):
        await service.send(recipient="Anna", message="hi")
    channel.send.assert_not_awaited()

    await service.send(recipient="anna petrova", message="hi")
    channel.send.assert_awaited_once_with(recipient="Anna Petrova", message="hi")


async def test_simulated_channel_returns_receipt_without_sending() -> None:
    # The concrete Strategy: it must SIMULATE (never actually send) and confirm.
    channel = SimulatedNotificationChannel()

    receipt = await channel.send(recipient="ops@example.com", message="Booking confirmed")

    assert receipt.status == "simulated"
    assert receipt.recipient == "ops@example.com"
    assert receipt.message_preview == "Booking confirmed"
