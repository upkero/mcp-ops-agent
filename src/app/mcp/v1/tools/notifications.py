from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from src.app.bootstrap.container import ApplicationContainer


def register(mcp: FastMCP, container: ApplicationContainer) -> None:
    """Register notification tools on the MCP server."""

    @mcp.tool()
    async def send_notification(
        recipient: Annotated[str, Field(min_length=1, description="Who to notify (name, email, or phone).")],
        message: Annotated[str, Field(min_length=1, max_length=2000, description="Message body to send.")],
    ) -> dict[str, object]:
        """Send a notification to a recipient.

        NOTE: delivery is SIMULATED — the call is logged and a receipt is
        returned, but no real message is sent anywhere.
        """
        receipt = await container.notification_service.send(
            recipient=recipient,
            message=message,
        )
        return {
            "status": receipt.status,
            "recipient": receipt.recipient,
            "message_preview": receipt.message_preview,
            "note": "simulated — no real message was sent",
        }
