from abc import ABC, abstractmethod

from src.app.contracts.notifications.receipt import NotificationReceipt


class NotificationChannel(ABC):
    """Delivery port: how a notification leaves the service.

    One implementation today, the simulated channel; the port is also the test
    seam. NotificationService calls ``send`` without knowing which channel it
    holds. Adding a real email/SMS channel later is a new implementation, not
    an edit to the service (Open/Closed).
    """

    @abstractmethod
    async def send(self, *, recipient: str, message: str) -> NotificationReceipt:
        """Deliver ``message`` to ``recipient`` and return a receipt."""
