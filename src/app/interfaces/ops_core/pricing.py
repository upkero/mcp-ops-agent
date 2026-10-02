from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.app.contracts.ops_core.price_quote import PriceQuote
from src.app.contracts.ops_core.priced_service import PricedService


class PricingGateway(ABC):
    """Port for service pricing, shaped like plain data access."""

    @abstractmethod
    async def quote(self, service: str, quantity: int) -> PriceQuote:
        """Return a priced quote for ``quantity`` units of ``service``.

        Raises OpsCoreNotFoundError when the service name is unknown.
        """

    @abstractmethod
    async def list_services(self) -> Sequence[PricedService]:
        """Return every service on the price list, with its unit price."""
