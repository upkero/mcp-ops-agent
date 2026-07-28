from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date

from src.app.contracts.ops_core.availability_slot import AvailabilitySlot
from src.app.contracts.ops_core.enums import ResourceType


class AvailabilityGateway(ABC):
    """Port for calendar-slot lookups in another service.

    Shaped like plain data access on purpose: nothing above it can tell whether
    the slots arrive over HTTP from ops-core-api or straight out of a table, so
    the availability service never changes when the backend does (Dependency
    Inversion / Open-Closed). It is a *gateway* rather than a repository because
    what it reaches is somebody else's service over the network — this repo owns
    no database at all.
    """

    @abstractmethod
    async def list_slots(
        self,
        *,
        slot_date: date,
        resource_type: ResourceType,
    ) -> Sequence[AvailabilitySlot]:
        """Return all slots for ``slot_date`` and ``resource_type``."""
