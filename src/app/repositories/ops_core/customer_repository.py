from collections.abc import Sequence
from typing import Any

import httpx

from src.app.contracts.ops_core.customer import Customer
from src.app.interfaces.ops_core.customers import CustomerRepository
from src.app.repositories.ops_core.base import ops_core_get


class OpsCoreCustomerRepository(CustomerRepository):
    """Adapter: ops-core-api /customers behind CustomerRepository.

    Adapter pattern — translates the wire schema into Customer contracts and maps
    a missing customer (404) to None, so the customer service never sees HTTP.
    """

    _BASE = "/api/v1/customers"

    def __init__(self, *, client: httpx.AsyncClient, max_attempts: int) -> None:
        self._client = client
        self._attempts = max_attempts

    async def get_by_id(self, customer_id: str) -> Customer | None:
        response = await ops_core_get(
            self._client,
            f"{self._BASE}/{customer_id}",
            attempts=self._attempts,
            allow_404=True,
        )
        if response is None:
            return None
        return self._to_customer(response.json())

    async def search(self, name: str) -> Sequence[Customer]:
        response = await ops_core_get(
            self._client,
            self._BASE,
            attempts=self._attempts,
            params={"search": name, "limit": 50},
        )
        assert response is not None  # allow_404 is False → 404 raises, never returns None
        return [self._to_customer(item) for item in response.json().get("items", [])]

    @staticmethod
    def _to_customer(item: dict[str, Any]) -> Customer:
        return Customer(
            id=item["id"],
            name=item["name"],
            status=item["status"],
            last_contact_at=item.get("last_contact_at"),
            notes=item.get("notes"),
        )
