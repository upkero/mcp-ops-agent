from abc import ABC, abstractmethod

from src.app.contracts.ops_core.price_quote import PriceQuote


class PricingGateway(ABC):
    """Port for service pricing, shaped like plain data access."""

    @abstractmethod
    async def quote(self, service: str, quantity: int) -> PriceQuote:
        """Return a priced quote for ``quantity`` units of ``service``.

        Raises OpsCoreNotFoundError when the service name is unknown.
        """
