"""Taking an order never waits on a geocoder.

These used to assert the opposite: create and edit awaited a provider and stored whatever pin
came back. That is now the sweeper's job (`test_geocode_pending`), and what the service owes
is the other half of the contract — leave the record in a state the sweeper will pick up.

Pure service-level tests with fakes — no network, no DB.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from restaurante.modules.delivery.application.use_cases.manage_delivery import (
    DeliveryService,
)
from restaurante.modules.delivery.domain.entities import OrderDelivery

TENANT = uuid.uuid4()
ORDER = uuid.uuid4()
BRANCH = uuid.uuid4()
DELIVERY = uuid.uuid4()


class FakeRepo:
    def __init__(self, *, existing: OrderDelivery | None = None) -> None:
        self._existing = existing
        self.created: OrderDelivery | None = None
        self.updated_fields: dict[str, Any] | None = None

    async def order_exists(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> bool:
        return True

    async def order_branch(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> uuid.UUID | None:
        return BRANCH

    async def get_delivery_by_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderDelivery | None:
        return None

    async def create_delivery(self, delivery: OrderDelivery) -> OrderDelivery:
        self.created = delivery
        return delivery

    async def get_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID
    ) -> OrderDelivery | None:
        return self._existing

    async def update_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderDelivery | None:
        self.updated_fields = fields
        d = self._existing
        assert d is not None
        return OrderDelivery(
            tenant_id=d.tenant_id,
            branch_id=d.branch_id,
            order_id=d.order_id,
            address_text=fields.get("address_text", d.address_text),
            neighborhood=fields.get("neighborhood", d.neighborhood),
            latitude=fields.get("latitude", d.latitude),
            longitude=fields.get("longitude", d.longitude),
        )

    async def apply_quote(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderDelivery | None:
        """Editing a location goes through here, not `update_delivery`.

        The real one also rewrites the order's frozen fee and total, which is why a location
        edit uses it: clearing the quote and clearing what was charged for it cannot be two
        separate writes. For these tests it is the same patch, recorded the same way.
        """
        return await self.update_delivery(tenant_id, delivery_id, fields)

    async def invalidate_payment_requests_for_delivery(
        self, tenant_id: uuid.UUID, order_delivery_id: uuid.UUID
    ) -> int:
        """A corrected address kills the link that quoted the old one."""
        self.invalidated_requests = getattr(self, "invalidated_requests", [])
        self.invalidated_requests.append(order_delivery_id)
        return 0


class ExplodingGeocoder:
    """The service must not hold one of these at all. If it calls anything, the test fails."""

    async def geocode(self, query: str, **kwargs: Any) -> None:
        raise AssertionError("the request path must never geocode")


def _existing(
    *, lat: Decimal | None = None, lon: Decimal | None = None
) -> OrderDelivery:
    return OrderDelivery(
        id=DELIVERY,
        tenant_id=TENANT,
        branch_id=BRANCH,
        order_id=ORDER,
        address_text="Calle 41A #12C-48",
        latitude=lat,
        longitude=lon,
    )


class TestCreate:
    async def test_create_does_not_geocode_and_returns_a_null_pin(self) -> None:
        """The record is born pin-less with an address — which is the sweeper's queue."""
        repo = FakeRepo()
        svc = DeliveryService(repo)  # type: ignore[arg-type]

        created = await svc.create_delivery(TENANT, ORDER, address_text="Calle 20")

        assert created.latitude is None
        assert created.longitude is None
        assert created.address_text == "Calle 20"

    async def test_the_service_takes_no_geocoder_at_all(self) -> None:
        """Not "doesn't call it" — doesn't have one. The dependency is gone, not disabled."""
        import inspect

        params = inspect.signature(DeliveryService.__init__).parameters
        assert "geocoder" not in params

    async def test_an_explicit_pin_is_stored_as_given(self) -> None:
        """The map picker: the operator placed it, so nothing may second-guess it."""
        repo = FakeRepo()
        svc = DeliveryService(repo)  # type: ignore[arg-type]

        created = await svc.create_delivery(
            TENANT,
            ORDER,
            address_text="Calle 20",
            latitude=Decimal("11.5"),
            longitude=Decimal("-72.9"),
        )

        assert (created.latitude, created.longitude) == (Decimal("11.5"), Decimal("-72.9"))


class TestUpdateAddress:
    async def test_a_new_address_clears_the_pin_so_the_sweeper_picks_it_up(self) -> None:
        """The old pin is on the old address. Clearing it re-enters the "needs a pin" set."""
        repo = FakeRepo(existing=_existing(lat=Decimal("11.52"), lon=Decimal("-72.90")))
        svc = DeliveryService(repo)  # type: ignore[arg-type]

        updated = await svc.update_delivery_address(
            TENANT, DELIVERY, {"address_text": "Carrera 7 #12-30"}
        )

        assert repo.updated_fields is not None
        assert repo.updated_fields["latitude"] is None
        assert repo.updated_fields["longitude"] is None
        assert updated.latitude is None

    async def test_an_explicit_pin_in_the_same_patch_survives(self) -> None:
        """Operator edits the address AND drops the pin: they win, and it is never swept."""
        repo = FakeRepo(existing=_existing(lat=Decimal("11.52"), lon=Decimal("-72.90")))
        svc = DeliveryService(repo)  # type: ignore[arg-type]

        updated = await svc.update_delivery_address(
            TENANT,
            DELIVERY,
            {
                "address_text": "Carrera 7 #12-30",
                "latitude": Decimal("11.6"),
                "longitude": Decimal("-72.8"),
            },
        )

        assert (updated.latitude, updated.longitude) == (Decimal("11.6"), Decimal("-72.8"))

    async def test_a_patch_that_does_not_touch_the_address_leaves_the_pin_alone(
        self,
    ) -> None:
        """Editing the notes must not throw away a pin somebody placed by hand."""
        repo = FakeRepo(existing=_existing(lat=Decimal("11.52"), lon=Decimal("-72.90")))
        svc = DeliveryService(repo)  # type: ignore[arg-type]

        updated = await svc.update_delivery_address(
            TENANT, DELIVERY, {"neighborhood": "Centro"}
        )

        assert repo.updated_fields is not None
        assert "latitude" not in repo.updated_fields
        assert updated.latitude == Decimal("11.52")
