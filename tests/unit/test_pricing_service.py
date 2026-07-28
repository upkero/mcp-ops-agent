from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.app.contracts.ops_core.price_quote import PriceQuote
from src.app.exceptions.ops_core import OpsCoreNotFoundError
from src.app.interfaces.ops_core.pricing import PricingGateway
from src.app.services.pricing import PricingService


def _service() -> tuple[PricingService, AsyncMock]:
    repo = AsyncMock(spec=PricingGateway)
    return PricingService(pricing=repo), repo


async def test_quote_delegates_to_the_gateway() -> None:
    service, repo = _service()
    repo.quote.return_value = PriceQuote(
        service_name="Deep Tissue Massage",
        unit_price=Decimal("120.00"),
        quantity=6,
        subtotal=Decimal("720.00"),
        discount_percent=Decimal("10"),
        discount_amount=Decimal("72.00"),
        total=Decimal("648.00"),
    )

    result = await service.quote(service="Deep Tissue Massage", quantity=6)

    repo.quote.assert_awaited_once_with("Deep Tissue Massage", 6)
    assert result.total == Decimal("648.00")


async def test_unknown_service_propagates_not_found() -> None:
    service, repo = _service()
    repo.quote.side_effect = OpsCoreNotFoundError()

    with pytest.raises(OpsCoreNotFoundError):
        await service.quote(service="No Such Service", quantity=1)
