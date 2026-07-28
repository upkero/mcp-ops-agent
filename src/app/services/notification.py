from src.app.contracts.notifications.receipt import NotificationReceipt
from src.app.interfaces.notifications.channel import NotificationChannel


class NotificationService:
    """Business logic for sending a notification.

    Delegates the actual delivery to an interchangeable NotificationChannel
    (Strategy) — the service picks *what* to send, the channel decides *how*.
    Depends on the NotificationChannel interface, so the simulated channel used
    here can be swapped for a real one without touching this class.
    """

    def __init__(self, *, channel: NotificationChannel) -> None:
        self._channel = channel

    async def send(self, *, recipient: str, message: str) -> NotificationReceipt:
        return await self._channel.send(recipient=recipient, message=message)
