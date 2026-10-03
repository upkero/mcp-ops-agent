from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from src.app.bootstrap.container import ApplicationContainer
from src.app.exceptions.notification import NotificationRecipientError


def register(mcp: FastMCP, container: ApplicationContainer) -> None:
    """Register notification tools on the MCP server."""

    @mcp.tool(
        description=(
            "Send a short notification to one existing customer. The recipient must be the "
            "customer id or full name returned by lookup_customer; anyone else is rejected. "
            "Only a few notifications are allowed per request. Never claim in the message "
            "that a booking or any other change was made. Delivery is SIMULATED: nothing is "
            "actually sent."
        )
    )
    async def send_notification(
        recipient: Annotated[
            str,
            Field(min_length=1, max_length=100, description="Customer id or full customer name."),
        ],
        message: Annotated[str, Field(min_length=1, max_length=1000, description="Message body to send.")],
    ) -> dict[str, object]:
        try:
            receipt = await container.notification_service.send(recipient=recipient, message=message)
        except NotificationRecipientError as exc:
            return {"status": "rejected", "error": exc.detail}
        return {
            "status": receipt.status,
            "recipient": receipt.recipient,
            "message_preview": receipt.message_preview,
            "note": "simulated — no real message was sent",
        }
