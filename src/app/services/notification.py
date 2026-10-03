from src.app.contracts.notifications.receipt import NotificationReceipt
from src.app.exceptions.notification import NotificationRecipientError
from src.app.interfaces.notifications.channel import NotificationChannel
from src.app.services.customer import CustomerService


class NotificationService:
    """Business logic for sending a notification.

    Delegates the actual delivery to an interchangeable NotificationChannel
    (Strategy) — the service picks *what* to send and *to whom*, the channel
    decides *how*. The recipient must be one existing customer, resolved through
    ops-core: free text is never forwarded, so a real channel added later cannot
    be pointed at an arbitrary address or phone number.
    """

    def __init__(self, *, channel: NotificationChannel, customers: CustomerService) -> None:
        self._channel = channel
        self._customers = customers

    async def send(self, *, recipient: str, message: str) -> NotificationReceipt:
        customer_name = await self._resolve(recipient)
        return await self._channel.send(recipient=customer_name, message=message)

    async def _resolve(self, recipient: str) -> str:
        matches = list(await self._customers.lookup(recipient))
        if len(matches) > 1:
            # "Anna" matching two customers is ambiguous; the full name is not.
            matches = [c for c in matches if c.name.casefold() == recipient.strip().casefold()]
        if len(matches) != 1:
            raise NotificationRecipientError(
                "Recipient is not exactly one existing customer. "
                "Use the id or full name returned by lookup_customer."
            )
        return matches[0].name
