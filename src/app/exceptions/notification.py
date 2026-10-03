from src.app.exceptions.base import BaseAppException


class NotificationRecipientError(BaseAppException):
    """The notification recipient is not exactly one existing customer.

    Raised for an unknown name or id and for a name that matches several customers.
    A business outcome the model can act on (ask who is meant), not a failure.
    """

    status_code = 422
    error_code = "notification_recipient_rejected"
    default_detail = "The recipient must be one existing customer."
