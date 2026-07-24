from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AvailabilityResult:
    """Booking service output: is a specific date/time/resource free?

    Carries enough for the agent to act on: whether a slot exists at all
    (``matched``), whether it is free (``available``), and — when it is not —
    other free times that day so the model can propose an alternative.
    """

    resource_type: str
    slot_date: str
    slot_time: str
    matched: bool
    available: bool
    capacity: int | None
    other_available_times: tuple[str, ...]
