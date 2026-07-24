from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PriceQuote:
    """A priced quote as returned by ops-core-api /pricing.

    Money fields are ``Decimal`` (parsed from the wire's JSON strings) — never
    floats — so rounding stays exact through the agent.
    """

    service_name: str
    unit_price: Decimal
    quantity: int
    subtotal: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    total: Decimal
