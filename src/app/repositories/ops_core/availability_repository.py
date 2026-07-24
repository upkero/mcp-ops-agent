import logging
from collections.abc import Sequence
from datetime import date
from typing import Any

import httpx

from src.app.contracts.ops_core.availability_slot import AvailabilitySlot
from src.app.contracts.ops_core.enums import ResourceType
from src.app.interfaces.ops_core.availability import AvailabilityRepository
from src.app.repositories.ops_core.base import ops_core_get

logger = logging.getLogger(__name__)


class OpsCoreAvailabilityRepository(AvailabilityRepository):
    """Adapter: ops-core-api GET /booking-slots behind AvailabilityRepository.

    Adapter pattern — wraps the shared httpx client and translates ops-core-api's
    wire schema into AvailabilitySlot contracts, so the booking service sees the
    same interface a direct-DB repository would expose. Every HTTP concern (URL,
    params, JSON shape) is contained here and never leaks upward.
    """

    _PATH = "/api/v1/booking-slots"

    def __init__(self, *, client: httpx.AsyncClient, max_retries: int) -> None:
        self._client = client
        self._attempts = max_retries + 1

    async def list_slots(
        self,
        *,
        slot_date: date,
        resource_type: ResourceType,
    ) -> Sequence[AvailabilitySlot]:
        response = await ops_core_get(
            self._client,
            self._PATH,
            attempts=self._attempts,
            params={"date": slot_date.isoformat(), "resource_type": resource_type, "limit": 200},
        )
        assert response is not None  # allow_404 is False → 404 raises, never returns None
        slots = [self._to_slot(item) for item in response.json().get("items", [])]
        logger.info(
            "ops_core.booking_slots",
            extra={
                "date": slot_date.isoformat(),
                "resource_type": resource_type,
                "slots_returned": len(slots),
            },
        )
        return slots

    @staticmethod
    def _to_slot(item: dict[str, Any]) -> AvailabilitySlot:
        # Boundary mapping: ops-core-api wire schema -> internal contract.
        return AvailabilitySlot(
            slot_id=item["id"],
            resource_type=item["resource_type"],
            slot_date=item["slot_date"],
            slot_time=item["slot_time"],
            capacity=item["capacity"],
            is_available=item["is_available"],
        )
