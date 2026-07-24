import logging

from src.app.contracts.ops_core.price_quote import PriceQuote
from src.app.interfaces.ops_core.pricing import PricingRepository

logger = logging.getLogger(__name__)


class PricingService:
    """Business logic for service quotes.

    Thin by design — the discount tiers live in ops-core-api — but it still owns
    the domain boundary: it depends on the PricingRepository interface, logs the
    quote, and lets an unknown service surface as a typed OpsCoreNotFoundError.
    """

    def __init__(self, *, pricing: PricingRepository) -> None:
        self._pricing = pricing

    async def quote(self, *, service: str, quantity: int) -> PriceQuote:
        result = await self._pricing.quote(service, quantity)
        logger.info(
            "pricing.quote",
            extra={"service": result.service_name, "quantity": result.quantity, "total": str(result.total)},
        )
        return result
