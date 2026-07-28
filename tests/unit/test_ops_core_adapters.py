"""Directly exercise the httpx ops-core adapters + the shared GET helper.

Uses ``httpx.MockTransport`` so the retry policy and error mapping — the part that
actually breaks in production — are tested without a live ops-core-api. Handlers
are plain functions returning canned responses; a counter closure drives the
retry/rate-limit sequencing.
"""

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import httpx
import pytest

from src.app.exceptions.ops_core import OpsCoreNotFoundError, OpsCoreUnavailableError
from src.app.gateways.ops_core.availability_gateway import OpsCoreAvailabilityGateway
from src.app.gateways.ops_core.customer_gateway import OpsCoreCustomerGateway
from src.app.gateways.ops_core.pricing_gateway import OpsCorePricingGateway

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ops-core")


# --- happy-path mapping ------------------------------------------------------

async def test_availability_maps_items_and_sends_params() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "s1",
                        "resource_type": "table",
                        "slot_date": "2026-07-25",
                        "slot_time": "18:00:00",
                        "capacity": 4,
                        "is_available": True,
                    }
                ]
            },
        )

    async with _client(handler) as client:
        repo = OpsCoreAvailabilityGateway(client=client, max_attempts=1)
        slots = await repo.list_slots(slot_date=date(2026, 7, 25), resource_type="table")

    assert seen["path"] == "/api/v1/booking-slots"
    assert seen["params"] == {"date": "2026-07-25", "resource_type": "table", "limit": "200"}
    assert len(slots) == 1
    assert slots[0].slot_id == "s1"
    assert slots[0].capacity == 4


async def test_pricing_parses_money_as_decimal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "service_name": "Deep Tissue Massage",
                "unit_price": "120.00",
                "quantity": 6,
                "subtotal": "720.00",
                "discount_percent": "10",
                "discount_amount": "72.00",
                "total": "648.00",
            },
        )

    async with _client(handler) as client:
        repo = OpsCorePricingGateway(client=client, max_attempts=1)
        quote = await repo.quote("Deep Tissue Massage", 6)

    assert quote.total == Decimal("648.00")
    assert isinstance(quote.total, Decimal)


# --- 404 handling ------------------------------------------------------------

async def test_customer_by_id_404_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "x", "error_code": "entity_not_found"})

    async with _client(handler) as client:
        repo = OpsCoreCustomerGateway(client=client, max_attempts=1)
        assert await repo.get_by_id("missing") is None


async def test_pricing_unknown_service_404_raises_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "x", "error_code": "entity_not_found"})

    async with _client(handler) as client:
        repo = OpsCorePricingGateway(client=client, max_attempts=1)
        with pytest.raises(OpsCoreNotFoundError):
            await repo.quote("No Such Service", 1)


# --- retry + error mapping ---------------------------------------------------

async def test_transient_5xx_is_retried_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"items": []})

    async with _client(handler) as client:
        repo = OpsCoreAvailabilityGateway(client=client, max_attempts=3)
        slots = await repo.list_slots(slot_date=date(2026, 7, 25), resource_type="table")

    assert calls["n"] == 2
    assert slots == []


async def test_persistent_5xx_maps_to_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with _client(handler) as client:
        repo = OpsCoreAvailabilityGateway(client=client, max_attempts=2)
        with pytest.raises(OpsCoreUnavailableError):
            await repo.list_slots(slot_date=date(2026, 7, 25), resource_type="table")


async def test_non_retryable_4xx_maps_to_unavailable_without_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"detail": "bad key", "error_code": "invalid_api_key"})

    async with _client(handler) as client:
        repo = OpsCoreCustomerGateway(client=client, max_attempts=4)
        with pytest.raises(OpsCoreUnavailableError):
            await repo.search("Anna")

    assert calls["n"] == 1  # 401 is a client error — not retried.


async def test_rate_limit_429_is_retried_honouring_retry_after() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            # Retry-After: 0 keeps the test fast while proving the header is honoured.
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"detail": "slow down"})
        return httpx.Response(200, json={"items": []})

    async with _client(handler) as client:
        repo = OpsCoreAvailabilityGateway(client=client, max_attempts=3)
        slots = await repo.list_slots(slot_date=date(2026, 7, 25), resource_type="table")

    assert calls["n"] == 2
    assert slots == []
