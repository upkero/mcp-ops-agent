from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NotificationReceipt:
    """Confirmation returned by a NotificationChannel after a (simulated) send."""

    status: str
    recipient: str
    message_preview: str
