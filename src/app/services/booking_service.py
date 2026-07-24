import logging
from datetime import date, time

from src.app.contracts.ops_core.availability_result import AvailabilityResult
from src.app.contracts.ops_core.enums import ResourceType
from src.app.interfaces.ops_core.availability import AvailabilityRepository

logger = logging.getLogger(__name__)


class BookingService:
    """Business logic for calendar availability checks.

    Depends only on the AvailabilityRepository *interface* (Dependency Inversion):
    a real HTTP adapter in production, an AsyncMock in unit tests. It turns a raw
    slot list into a decision the agent can act on — matched? available? which
    other times are free — rather than passing the wire data through untouched.
    """

    def __init__(self, *, availability: AvailabilityRepository) -> None:
        self._availability = availability

    async def check_availability(
        self,
        *,
        slot_date: date,
        slot_time: time,
        resource_type: ResourceType,
    ) -> AvailabilityResult:
        slots = await self._availability.list_slots(slot_date=slot_date, resource_type=resource_type)

        wanted = slot_time.strftime("%H:%M")
        matched = next((slot for slot in slots if slot.slot_time.startswith(wanted)), None)
        other_available = tuple(
            slot.slot_time[:5]
            for slot in slots
            if slot.is_available and (matched is None or slot.slot_id != matched.slot_id)
        )

        result = AvailabilityResult(
            resource_type=resource_type,
            slot_date=slot_date.isoformat(),
            slot_time=wanted,
            matched=matched is not None,
            available=bool(matched and matched.is_available),
            capacity=matched.capacity if matched else None,
            other_available_times=other_available,
        )
        logger.info(
            "booking.check_availability",
            extra={
                "date": result.slot_date,
                "time": result.slot_time,
                "resource_type": resource_type,
                "matched": result.matched,
                "available": result.available,
            },
        )
        return result
