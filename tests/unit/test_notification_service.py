from unittest.mock import AsyncMock

from src.app.contracts.notifications.receipt import NotificationReceipt
from src.app.gateways.notifications.simulated_channel import SimulatedNotificationChannel
from src.app.interfaces.notifications.channel import NotificationChannel
from src.app.services.notification import NotificationService


async def test_send_delegates_to_channel() -> None:
    channel = AsyncMock(spec=NotificationChannel)
    channel.send.return_value = NotificationReceipt("simulated", "Anna", "hi")
    service = NotificationService(channel=channel)

    receipt = await service.send(recipient="Anna", message="hi")

    channel.send.assert_awaited_once_with(recipient="Anna", message="hi")
    assert receipt.status == "simulated"


async def test_simulated_channel_returns_receipt_without_sending() -> None:
    # The concrete Strategy: it must SIMULATE (never actually send) and confirm.
    channel = SimulatedNotificationChannel()

    receipt = await channel.send(recipient="ops@example.com", message="Booking confirmed")

    assert receipt.status == "simulated"
    assert receipt.recipient == "ops@example.com"
    assert receipt.message_preview == "Booking confirmed"
