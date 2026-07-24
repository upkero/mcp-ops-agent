from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date

from src.app.contracts.ops_core.availability_slot import AvailabilitySlot
from src.app.contracts.ops_core.enums import ResourceType


class AvailabilityRepository(ABC):
    """Repository-style abstraction over calendar-slot lookups.

    It looks like data access on purpose: an HTTP adapter (ops-core-api) and a
    hypothetical direct-DB repository are interchangeable behind it, so the
    booking service never changes when the backend does (Dependency Inversion /
    Open-Closed).
    """

    @abstractmethod
    async def list_slots(
        self,
        *,
        slot_date: date,
        resource_type: ResourceType,
    ) -> Sequence[AvailabilitySlot]:
        """Return all slots for ``slot_date`` and ``resource_type``."""
