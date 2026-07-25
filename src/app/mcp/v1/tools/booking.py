# Aliased so the tool can name its parameters `date`/`time` (the argument names in
# the JSON Schema) without those names shadowing the datetime types in annotations.
from datetime import date as Date
from datetime import time as Time
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from src.app.bootstrap.container import ApplicationContainer
from src.app.contracts.ops_core.enums import ResourceType


def register(mcp: FastMCP, container: ApplicationContainer) -> None:
    """Register booking tools on the MCP server (mirrors including an API sub-router)."""

    @mcp.tool()
    async def check_calendar_availability(
        date: Annotated[Date, Field(description="Calendar date to check, ISO 8601 (YYYY-MM-DD).")],
        time: Annotated[Time, Field(description="Start time to check, 24-hour HH:MM.")],
        resource_type: Annotated[ResourceType, Field(description="Resource kind: 'table' or 'meeting_room'.")],
    ) -> dict[str, object]:
        """Check whether a calendar slot is free for a date, time and resource type.

        Returns whether a matching slot exists, whether it is available, its
        capacity, and other free times that day.

        FastMCP derives (and validates) the JSON Schema from these typed
        parameters — the schema is never hand-written, and a bad value (unknown
        resource type, malformed date) is rejected before the service runs.
        """
        result = await container.booking_service.check_availability(
            slot_date=date,
            slot_time=time,
            resource_type=resource_type,
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
