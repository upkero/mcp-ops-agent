from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from src.app.bootstrap.container import ApplicationContainer


class LookupCustomerArgs(BaseModel):
    """Validated arguments for lookup_customer."""

    name_or_id: str = Field(
        min_length=1,
        description="Customer name fragment (case-insensitive) or an exact customer UUID.",
    )


def register(mcp: FastMCP, container: ApplicationContainer) -> None:
    """Register customer tools on the MCP server."""

    @mcp.tool()
    async def lookup_customer(args: LookupCustomerArgs) -> dict[str, object]:
        """Look up customers by name fragment or by exact id.

        Returns every matching customer (a UUID resolves to at most one).
        """
        customers = await container.customer_service.lookup(args.name_or_id)
        return {
            "count": len(customers),
            "customers": [
                {
                    "id": customer.id,
                    "name": customer.name,
                    "status": customer.status,
                    "last_contact_at": customer.last_contact_at,
                    "notes": customer.notes,
                }
                for customer in customers
            ],
        }
