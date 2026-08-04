"""Announcing a delivery for geocoding — with a fake queue. No Redis, no worker, no network.

The announcement is a hint, and these tests are mostly about what it must NOT do. It must not
be sent for a record the resolver would never touch (that would be a lie the worker re-checks),
and it must never, under any failure, cost the order that produced it.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest

from restaurante.modules.delivery.application.use_cases.manage_delivery import (
    DeliveryService,
)
from restaurante.modules.delivery.domain.entities import OrderDelivery

TENANT = uuid.uuid4()
BRANCH = uuid.uuid4()
ORDER = uuid.uuid4()

PIN = (Decimal("11.5444"), Decimal("-72.9072"))


class FakeQueue:
    def __init__(self, *, explodes: bool = False) -> None:
        self._explodes = explodes
        self.announced: list[tuple[uuid.UUID, uuid.UUID]] = []
        self.quotes_announced: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def announce(self, tenant_id: uuid.UUID, delivery_id: uuid.UUID) -> None:
        if self._explodes:
            raise RuntimeError("redis is not there")
        self.announced.append((tenant_id, delivery_id))

    async def announce_quote(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID
    ) -> None:
        if self._explodes:
            raise RuntimeError("redis is not there")
        self.quotes_announced.append((tenant_id, delivery_id))


class FakeRepo:
    """Only what the two announcing paths touch."""

    def __init__(self, *, existing: OrderDelivery | None = None) -> None:
        self._existing = existing
        self.created: OrderDelivery | None = None

    async def order_branch(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> uuid.UUID | None:
        return BRANCH

    async def get_delivery_by_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderDelivery | None:
        return None

    async def create_delivery(self, delivery: OrderDelivery) -> OrderDelivery:
        stored = OrderDelivery(
            id=uuid.uuid4(),
            tenant_id=delivery.tenant_id,
            branch_id=delivery.branch_id,
            order_id=delivery.order_id,
            address_text=delivery.address_text,
            neighborhood=delivery.neighborhood,
            latitude=delivery.latitude,
            longitude=delivery.longitude,
        )
        self.created = stored
        return stored

    async def get_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID
    ) -> OrderDelivery | None:
        return self._existing

    async def update_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderDelivery | None:
        assert self._existing is not None
        return OrderDelivery(
            id=self._existing.id,
            tenant_id=self._existing.tenant_id,
            branch_id=self._existing.branch_id,
            order_id=self._existing.order_id,
            address_text=fields.get("address_text", self._existing.address_text),
            neighborhood=self._existing.neighborhood,
            latitude=fields.get("latitude", self._existing.latitude),
            longitude=fields.get("longitude", self._existing.longitude),
        )

    async def apply_quote(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderDelivery | None:
        """A location edit writes through here: it clears the quote and the frozen fee in one
        unit of work. Same patch, same recording, for the purposes of these tests."""
        return await self.update_delivery(tenant_id, delivery_id, fields)

    async def invalidate_payment_requests_for_delivery(
        self, tenant_id: uuid.UUID, order_delivery_id: uuid.UUID
    ) -> int:
        """A corrected address kills the link that quoted the old one."""
        self.invalidated_requests = getattr(self, "invalidated_requests", [])
        self.invalidated_requests.append(order_delivery_id)
        return 0


def _service(repo: FakeRepo, queue: FakeQueue | None) -> DeliveryService:
    return DeliveryService(repo, geocode_queue=queue)  # type: ignore[arg-type]


def _stored(
    *,
    address: str = "Calle 41A #12C-48",
    latitude: Decimal | None = None,
    longitude: Decimal | None = None,
) -> OrderDelivery:
    return OrderDelivery(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        branch_id=BRANCH,
        order_id=ORDER,
        address_text=address,
        latitude=latitude,
        longitude=longitude,
    )


class TestCreate:
    @pytest.mark.asyncio
    async def test_an_address_with_no_pin_is_announced_exactly_once(self) -> None:
        repo, queue = FakeRepo(), FakeQueue()
        delivery = await _service(repo, queue).create_delivery(
            TENANT, ORDER, "Calle 41A #12C-48"
        )

        assert delivery.id is not None
        assert queue.announced == [(TENANT, delivery.id)]

    @pytest.mark.asyncio
    async def test_an_explicit_pin_is_never_announced_for_geocoding(self) -> None:
        """The map picker placed it. It is never swept, so announcing it would be a lie."""
        repo, queue = FakeRepo(), FakeQueue()
        await _service(repo, queue).create_delivery(
            TENANT, ORDER, "Calle 41A #12C-48", latitude=PIN[0], longitude=PIN[1]
        )

        assert queue.announced == []

    @pytest.mark.asyncio
    async def test_an_explicit_pin_IS_announced_for_quoting(self) -> None:
        """A GPS order has everything the quoter needs the instant it is taken.

        Without this it waits a full sweep tick for a Haversine — the customer sits there not
        knowing what the delivery costs, for a calculation that takes microseconds.
        """
        repo, queue = FakeRepo(), FakeQueue()
        delivery = await _service(repo, queue).create_delivery(
            TENANT, ORDER, "Calle 41A #12C-48", latitude=PIN[0], longitude=PIN[1]
        )

        assert delivery.id is not None
        assert queue.quotes_announced == [(TENANT, delivery.id)]

    @pytest.mark.asyncio
    async def test_a_pinless_address_announces_geocoding_and_not_quoting(self) -> None:
        """Nothing to quote yet: the pin is what the quoter is waiting for."""
        repo, queue = FakeRepo(), FakeQueue()
        await _service(repo, queue).create_delivery(TENANT, ORDER, "Calle 41A #12C-48")

        assert queue.announced and queue.quotes_announced == []

    @pytest.mark.asyncio
    async def test_a_dead_queue_does_not_fail_a_gps_order(self) -> None:
        """The sweep still prices it, so the announcement may never reach the caller."""
        repo = FakeRepo()
        delivery = await _service(repo, FakeQueue(explodes=True)).create_delivery(
            TENANT, ORDER, "Calle 41A #12C-48", latitude=PIN[0], longitude=PIN[1]
        )

        assert delivery.id is not None

    @pytest.mark.asyncio
    async def test_an_address_of_spaces_is_not_announced(self) -> None:
        """`btrim(address_text) <> ''` — it is not in the set, so there is nothing to say."""
        repo, queue = FakeRepo(), FakeQueue()
        await _service(repo, queue).create_delivery(TENANT, ORDER, "   ")

        assert queue.announced == []


class TestAnAnnouncementNeverCostsTheOrder:
    @pytest.mark.asyncio
    async def test_a_queue_that_raises_does_not_fail_the_create(self) -> None:
        """Spec: "An announcement that cannot be sent does not fail the order".

        The pin is not lost by this — the record has an address and no location, so the
        periodic pass owns it. That is the only reason swallowing here is honest.
        """
        repo = FakeRepo()
        delivery = await _service(repo, FakeQueue(explodes=True)).create_delivery(
            TENANT, ORDER, "Calle 41A #12C-48"
        )

        assert delivery.id is not None
        assert repo.created is not None
        # And the record really is in the resolver's set, which is what redeems the swallow.
        assert delivery.latitude is None and delivery.address_text.strip()


class TestWithNoQueue:
    @pytest.mark.asyncio
    async def test_the_service_behaves_exactly_as_before(self) -> None:
        """No queue is not an error: the pass still pins it, just not as fast."""
        repo = FakeRepo()
        delivery = await _service(repo, None).create_delivery(
            TENANT, ORDER, "Calle 41A #12C-48"
        )

        assert delivery.id is not None
        assert delivery.latitude is None


class TestAddressEdit:
    @pytest.mark.asyncio
    async def test_a_new_address_clears_the_pin_and_is_announced(self) -> None:
        existing = _stored(latitude=PIN[0], longitude=PIN[1])
        repo, queue = FakeRepo(existing=existing), FakeQueue()
        updated = await _service(repo, queue).update_delivery_address(
            TENANT, existing.id, {"address_text": "Carrera 15 #10-20"}  # type: ignore[arg-type]
        )

        assert updated.latitude is None
        assert queue.announced == [(TENANT, existing.id)]

    @pytest.mark.asyncio
    async def test_an_explicit_pin_in_the_same_patch_survives_and_is_not_announced(
        self,
    ) -> None:
        """The operator moved the pin by hand while fixing the address. Theirs wins."""
        existing = _stored()
        repo, queue = FakeRepo(existing=existing), FakeQueue()
        updated = await _service(repo, queue).update_delivery_address(
            TENANT,
            existing.id,  # type: ignore[arg-type]
            {
                "address_text": "Carrera 15 #10-20",
                "latitude": PIN[0],
                "longitude": PIN[1],
            },
        )

        assert updated.latitude == PIN[0]
        assert queue.announced == []

    @pytest.mark.asyncio
    async def test_an_untouched_address_is_not_announced(self) -> None:
        """Nothing entered the set: a pin-less record was already announced when written."""
        existing = _stored()
        repo, queue = FakeRepo(existing=existing), FakeQueue()
        await _service(repo, queue).update_delivery_address(
            TENANT, existing.id, {"neighborhood": "Centro"}  # type: ignore[arg-type]
        )

        assert queue.announced == []
