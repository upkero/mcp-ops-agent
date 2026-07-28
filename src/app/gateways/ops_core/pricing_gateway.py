from decimal import Decimal
from typing import Any

import httpx

from src.app.contracts.ops_core.price_quote import PriceQuote
from src.app.gateways.ops_core.base import ops_core_get
from src.app.interfaces.ops_core.pricing import PricingGateway


class OpsCorePricingGateway(PricingGateway):
    """Adapter: ops-core-api GET /pricing behind PricingGateway.

    Adapter pattern — parses the wire's money strings into Decimals (never floats)
    and lets an unknown service surface as OpsCoreNotFoundError via the shared GET.
    """

    _PATH = "/api/v1/pricing"

    def __init__(self, *, client: httpx.AsyncClient, max_attempts: int) -> None:
        self._client = client
        self._attempts = max_attempts

    async def quote(self, service: str, quantity: int) -> PriceQuote:
        response = await ops_core_get(
            self._client,
            self._PATH,
            attempts=self._attempts,
            params={"service": service, "quantity": quantity},
        )
        assert response is not None  # unknown service → 404 already raised OpsCoreNotFoundError
        return self._to_quote(response.json())

    @staticmethod
    def _to_quote(body: dict[str, Any]) -> PriceQuote:
        # ops-core-api serialises money as JSON strings — Decimal(str(...)) keeps
        # them exact whether they arrive as strings or numbers.
        return PriceQuote(
            service_name=body["service_name"],
            unit_price=Decimal(str(body["unit_price"])),
            quantity=body["quantity"],
            subtotal=Decimal(str(body["subtotal"])),
            discount_percent=Decimal(str(body["discount_percent"])),
            discount_amount=Decimal(str(body["discount_amount"])),
            total=Decimal(str(body["total"])),
        )
