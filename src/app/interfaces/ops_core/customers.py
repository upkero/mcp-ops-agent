from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.app.contracts.ops_core.customer import Customer


class CustomerRepository(ABC):
    """Repository-style abstraction over CRM customer access."""

    @abstractmethod
    async def get_by_id(self, customer_id: str) -> Customer | None:
        """Return the customer with ``customer_id``, or None if absent."""

    @abstractmethod
    async def search(self, name: str) -> Sequence[Customer]:
        """Return customers whose name matches ``name`` (case-insensitive fragment)."""
