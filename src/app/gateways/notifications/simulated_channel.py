import logging

from src.app.contracts.notifications.receipt import NotificationReceipt
from src.app.interfaces.notifications.channel import NotificationChannel

logger = logging.getLogger(__name__)


class SimulatedNotificationChannel(NotificationChannel):
    """The NotificationChannel that SIMULATES delivery — logs it and returns a receipt.

    It intentionally sends nothing: the notification tool demonstrates the agent
    loop without wiring a real email/SMS provider. The ``simulation`` log flag
    makes that explicit. A real channel is a new NotificationChannel beside this
    one, so this simulation stays available to the tests.
    """

    async def send(self, *, recipient: str, message: str) -> NotificationReceipt:
        # The length, not the text, and no recipient: both are a customer's personal data,
        # and the receipt below already carries them back to the caller.
        logger.info(
            "notification.simulated",
            extra={
                "message_length": len(message),
                "delivered": False,
                "simulation": True,
            },
        )
        return NotificationReceipt(
            status="simulated",
            recipient=recipient,
            message_preview=message[:120],
        )
