import logging

from src.app.contracts.notifications.receipt import NotificationReceipt
from src.app.interfaces.notifications.channel import NotificationChannel

logger = logging.getLogger(__name__)


class SimulatedNotificationChannel(NotificationChannel):
    """Strategy impl that SIMULATES delivery — logs it and returns a receipt.

    It intentionally sends nothing: the notification tool demonstrates the agent
    loop without wiring a real email/SMS provider. The ``simulation`` log flag
    makes that explicit. Swapping in a real channel is a new NotificationChannel,
    not an edit here (Open/Closed).
    """

    async def send(self, *, recipient: str, message: str) -> NotificationReceipt:
        logger.info(
            "notification.simulated",
            extra={
                "recipient": recipient,
                "message_preview": message[:80],
                "delivered": False,
                "simulation": True,
            },
        )
        return NotificationReceipt(
            status="simulated",
            recipient=recipient,
            message_preview=message[:120],
        )
