from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AvailabilitySlot:
    """A bookable calendar slot as returned by ops-core-api /booking-slots.

    Times are kept as the wire strings (``"18:00:00"``); interpreting them is the
    booking service's job, not this DTO's.
    """

    slot_id: str
    resource_type: str
    slot_date: str
    slot_time: str
    capacity: int
    is_available: bool
