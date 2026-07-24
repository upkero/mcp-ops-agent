from abc import ABC, abstractmethod

from src.app.contracts.notifications.receipt import NotificationReceipt


class NotificationChannel(ABC):
    """Strategy: an interchangeable notification-delivery behaviour.

    NotificationService holds one NotificationChannel and calls ``send`` without
    knowing which concrete strategy it is. Adding a real email/SMS channel later
    is a new implementation, not an edit to the service (Open/Closed).
    """

    @abstractmethod
    async def send(self, *, recipient: str, message: str) -> NotificationReceipt:
        """Deliver ``message`` to ``recipient`` and return a receipt."""
