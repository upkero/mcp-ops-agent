from abc import ABC, abstractmethod

from src.app.contracts.ops_core.price_quote import PriceQuote


class PricingRepository(ABC):
    """Repository-style abstraction over service pricing."""

    @abstractmethod
    async def quote(self, service: str, quantity: int) -> PriceQuote:
        """Return a priced quote for ``quantity`` units of ``service``.

        Raises OpsCoreNotFoundError when the service name is unknown.
        """
