from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from src.app.bootstrap.container import ApplicationContainer


class SendNotificationArgs(BaseModel):
    """Validated arguments for send_notification."""

    recipient: str = Field(min_length=1, description="Who to notify (name, email, or phone).")
    message: str = Field(min_length=1, max_length=2000, description="Message body to send.")


def register(mcp: FastMCP, container: ApplicationContainer) -> None:
    """Register notification tools on the MCP server."""

    @mcp.tool()
    async def send_notification(args: SendNotificationArgs) -> dict[str, object]:
        """Send a notification to a recipient.

        NOTE: delivery is SIMULATED — the call is logged and a receipt is
        returned, but no real message is sent anywhere.
        """
        receipt = await container.notification_service.send(
            recipient=args.recipient,
            message=args.message,
        )
        return {
            "status": receipt.status,
            "recipient": receipt.recipient,
            "message_preview": receipt.message_preview,
            "note": "simulated — no real message was sent",
        }
