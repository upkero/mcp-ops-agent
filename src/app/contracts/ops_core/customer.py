from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Customer:
    """A CRM customer as returned by ops-core-api /customers."""

    id: str
    name: str
    status: str
    last_contact_at: str | None
    notes: str | None
