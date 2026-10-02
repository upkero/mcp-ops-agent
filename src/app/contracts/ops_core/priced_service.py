from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PricedService:
    """One line of ops-core-api's price list: the exact name a quote must use."""

    service_name: str
    unit_price: Decimal
