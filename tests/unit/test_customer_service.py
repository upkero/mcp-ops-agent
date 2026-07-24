from unittest.mock import AsyncMock

from src.app.contracts.ops_core.customer import Customer
from src.app.interfaces.ops_core.customers import CustomerRepository
from src.app.services.customer_service import CustomerService

_UUID = "123e4567-e89b-12d3-a456-426614174000"


def _service() -> tuple[CustomerService, AsyncMock]:
    repo = AsyncMock(spec=CustomerRepository)
    return CustomerService(customers=repo), repo


async def test_name_input_uses_search() -> None:
    service, repo = _service()
    repo.search.return_value = [Customer("id1", "Anna Petrova", "active", None, None)]

    result = await service.lookup("Anna")

    repo.search.assert_awaited_once_with("Anna")
    repo.get_by_id.assert_not_awaited()
    assert [customer.name for customer in result] == ["Anna Petrova"]


async def test_uuid_input_fetches_by_id() -> None:
    service, repo = _service()
    repo.get_by_id.return_value = Customer(_UUID, "Anna Petrova", "active", None, None)

    result = await service.lookup(_UUID)

    repo.get_by_id.assert_awaited_once_with(_UUID)
    repo.search.assert_not_awaited()
    assert len(result) == 1


async def test_uuid_not_found_returns_empty() -> None:
    service, repo = _service()
    repo.get_by_id.return_value = None

    result = await service.lookup(_UUID)

    assert result == []
