from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from src.app.bootstrap.container import ApplicationContainer
from src.app.exceptions.ops_core import OpsCoreNotFoundError


def register(mcp: FastMCP, container: ApplicationContainer) -> None:
    """Register pricing tools on the MCP server."""

    @mcp.tool()
    async def list_services() -> dict[str, object]:
        """List every service on the price list with its unit price.

        Names are in English. Call this first when the user names a service in
        another language or loosely, then pass the exact name to calculate_quote.
        """
        services = await container.pricing_service.list_services()
        return {"services": [{"name": item.service_name, "unit_price": str(item.unit_price)} for item in services]}

    @mcp.tool()
    async def calculate_quote(
        service: Annotated[str, Field(min_length=1, description="Exact service name to price, as returned by list_services.")],
        quantity: Annotated[int, Field(ge=1, le=1000, description="Number of units/sessions to quote.")],
    ) -> dict[str, object]:
        """Calculate a price quote for a service and quantity (volume discounts apply).

        Money is returned as strings to stay exact. If the service name is
        unknown, ``found`` is false with a short explanation.
        """
        try:
            quote = await container.pricing_service.quote(service=service, quantity=quantity)
        except OpsCoreNotFoundError:
            # A business "not found" outcome — reported to the model, not raised,
            # so it can correct the service name and try again.
            return {
                "found": False,
                "error": f"Unknown service '{service}'. Call list_services for the exact names.",
            }

        return {
            "found": True,
            "service_name": quote.service_name,
            "unit_price": str(quote.unit_price),
            "quantity": quote.quantity,
            "subtotal": str(quote.subtotal),
            "discount_percent": str(quote.discount_percent),
            "discount_amount": str(quote.discount_amount),
            "total": str(quote.total),
        }
