from dataclasses import asdict
from decimal import Decimal
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from src.app.bootstrap.container import ApplicationContainer
from src.app.exceptions.ops_core import OpsCoreNotFoundError


def register(mcp: FastMCP, container: ApplicationContainer) -> None:
    """Register pricing tools on the MCP server."""

    @mcp.tool(
        description=(
            "List every service on the price list with its unit price. Names are in English. "
            "Call this first when the user names a service in another language or loosely, "
            "then pass the exact name to calculate_quote."
        )
    )
    async def list_services() -> dict[str, object]:
        services = await container.pricing_service.list_services()
        return {"services": [{"name": item.service_name, "unit_price": str(item.unit_price)} for item in services]}

    @mcp.tool(
        description=(
            "Calculate a price quote for a service and quantity (volume discounts apply). "
            "Money is returned as strings to stay exact. If the service name is unknown, "
            "`found` is false with a short explanation."
        )
    )
    async def calculate_quote(
        service: Annotated[
            str, Field(min_length=1, description="Exact service name to price, as returned by list_services.")
        ],
        quantity: Annotated[int, Field(ge=1, le=1000, description="Number of units/sessions to quote.")],
    ) -> dict[str, object]:
        try:
            quote = await container.pricing_service.quote(service=service, quantity=quantity)
        except OpsCoreNotFoundError:
            # A business "not found" outcome — reported to the model, not raised,
            # so it can correct the service name and try again.
            return {
                "found": False,
                "error": f"Unknown service '{service}'. Call list_services for the exact names.",
            }

        # Money as strings: a Decimal has no JSON form, and a float would round it.
        fields = asdict(quote)
        return {"found": True, **{k: str(v) if isinstance(v, Decimal) else v for k, v in fields.items()}}
