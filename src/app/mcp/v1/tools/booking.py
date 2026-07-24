# Aliased so the model can name its fields `date`/`time` (the tool's argument
# names) without those field names shadowing the datetime types in annotations.
from datetime import date as Date
from datetime import time as Time

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from src.app.bootstrap.container import ApplicationContainer
from src.app.contracts.ops_core.enums import ResourceType


class CheckAvailabilityArgs(BaseModel):
    """Validated arguments for check_calendar_availability.

    FastMCP derives the tool's JSON Schema from this model (types + docstrings) —
    the schema is never hand-written, and these constraints reject bad arguments
    before the service ever runs.
    """

    date: Date = Field(description="Calendar date to check, ISO 8601 (YYYY-MM-DD).")
    time: Time = Field(description="Start time to check, 24-hour HH:MM.")
    resource_type: ResourceType = Field(description="Resource kind: 'table' or 'meeting_room'.")


def register(mcp: FastMCP, container: ApplicationContainer) -> None:
    """Register booking tools on the MCP server (mirrors including an API sub-router)."""

    @mcp.tool()
    async def check_calendar_availability(args: CheckAvailabilityArgs) -> dict[str, object]:
        """Check whether a calendar slot is free for a date, time and resource type.

        Returns whether a matching slot exists, whether it is available, its
        capacity, and other free times that day.
        """
        result = await container.booking_service.check_availability(
            slot_date=args.date,
            slot_time=args.time,
            resource_type=args.resource_type,
        )
        return {
            "resource_type": result.resource_type,
            "date": result.slot_date,
            "time": result.slot_time,
            "matched": result.matched,
            "available": result.available,
            "capacity": result.capacity,
            "other_available_times": list(result.other_available_times),
        }
