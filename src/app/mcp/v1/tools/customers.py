from dataclasses import asdict
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from src.app.bootstrap.container import ApplicationContainer


def register(mcp: FastMCP, container: ApplicationContainer) -> None:
    """Register customer tools on the MCP server."""

    @mcp.tool(
        description=(
            "Look up customers by name fragment or by exact id. "
            "Returns every matching customer (a UUID resolves to at most one)."
        )
    )
    async def lookup_customer(
        name_or_id: Annotated[
            str,
            Field(min_length=1, description="Customer name fragment (case-insensitive) or an exact customer UUID."),
        ],
    ) -> dict[str, object]:
        customers = await container.customer_service.lookup(name_or_id)
        return {"count": len(customers), "customers": [asdict(customer) for customer in customers]}
