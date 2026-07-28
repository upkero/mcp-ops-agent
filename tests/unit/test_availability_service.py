from datetime import date, time
from unittest.mock import AsyncMock

from src.app.contracts.ops_core.availability_slot import AvailabilitySlot
from src.app.interfaces.ops_core.availability import AvailabilityGateway
from src.app.services.availability import AvailabilityService


def _service(slots: list[AvailabilitySlot]) -> tuple[AvailabilityService, AsyncMock]:
    repo = AsyncMock(spec=AvailabilityGateway)  # spec => Liskov-safe double
    repo.list_slots.return_value = slots
    return AvailabilityService(availability=repo), repo


async def test_matched_available_slot_reports_capacity_and_alternatives() -> None:
    service, repo = _service(
        [
            AvailabilitySlot("s1", "table", "2026-07-25", "18:00:00", 4, True),
            AvailabilitySlot("s2", "table", "2026-07-25", "19:30:00", 6, True),
        ]
    )

    result = await service.check_availability(
        slot_date=date(2026, 7, 25), slot_time=time(18, 0), resource_type="table"
    )

    repo.list_slots.assert_awaited_once_with(slot_date=date(2026, 7, 25), resource_type="table")
    assert result.matched is True
    assert result.available is True
    assert result.capacity == 4
    assert result.other_available_times == ("19:30",)


async def test_no_slot_at_time_is_unmatched() -> None:
    service, _ = _service([AvailabilitySlot("s1", "table", "2026-07-25", "18:00:00", 4, True)])

    result = await service.check_availability(
        slot_date=date(2026, 7, 25), slot_time=time(20, 0), resource_type="table"
    )

    assert result.matched is False
    assert result.available is False
    assert result.capacity is None
    # The 18:00 slot is free, so it is offered as an alternative.
    assert result.other_available_times == ("18:00",)


async def test_matched_but_unavailable_slot() -> None:
    service, _ = _service([AvailabilitySlot("s1", "meeting_room", "2026-07-25", "09:00:00", 10, False)])

    result = await service.check_availability(
        slot_date=date(2026, 7, 25), slot_time=time(9, 0), resource_type="meeting_room"
    )

    assert result.matched is True
    assert result.available is False
    # An unavailable slot is never suggested as an alternative.
    assert result.other_available_times == ()
