import logging
from collections.abc import Sequence
from uuid import UUID

from src.app.contracts.ops_core.customer import Customer
from src.app.interfaces.ops_core.customers import CustomerGateway

logger = logging.getLogger(__name__)


class CustomerService:
    """Business logic for customer lookup by name OR id.

    Chooses the right gateway call based on the input shape (UUID → direct
    fetch, otherwise a name search), and always returns a uniform list so the
    caller need not care which path ran. Depends on the CustomerGateway
    interface only (Dependency Inversion).
    """

    def __init__(self, *, customers: CustomerGateway) -> None:
        self._customers = customers

    async def lookup(self, name_or_id: str) -> Sequence[Customer]:
        as_uuid = self._parse_uuid(name_or_id)
        if as_uuid is not None:
            customer = await self._customers.get_by_id(str(as_uuid))
            found = [customer] if customer is not None else []
        else:
            found = list(await self._customers.search(name_or_id))

        logger.info(
            "customer.lookup",
            extra={"by_id": as_uuid is not None, "results": len(found)},
        )
        return found

    @staticmethod
    def _parse_uuid(value: str) -> UUID | None:
        try:
            return UUID(value.strip())
        except ValueError:
            return None
