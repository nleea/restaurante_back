"""`cancelled`: el tercer desenlace de una entrega, y qué deja de bloquear.

Una entrega cuya comanda se canceló nunca salió del local. Antes no tenía salida honesta: o se
quedaba `pending` bloqueando la caja del turno para siempre, o alguien la marcaba "no entregada",
que es mentira y ensucia las cifras de la operación.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.delivery.application.use_cases.manage_delivery import (
    D_CANCELLED,
    D_TERMINAL,
    D_UNRESOLVED,
    DeliveryService,
)
from restaurante.modules.delivery.domain.entities import (
    DELIVERY_NOT_DELIVERED,
    OrderDelivery,
)
from restaurante.modules.delivery.infrastructure.models import OrderDeliveryModel
from restaurante.shared.database import SessionFactory
from restaurante.shared.domain.errors import ConflictError
from tests.modules._cash import seed_open_cash_session
from tests.modules.storefront._seed import (
    seed_delivery_ready,
    seed_menu,
    seed_primary_branch,
)

TENANT = uuid.uuid4()


class TestTheStateItself:
    def test_cancelled_is_terminal(self) -> None:
        assert D_CANCELLED in D_TERMINAL
        assert D_CANCELLED not in D_UNRESOLVED

    def test_cancelled_is_not_a_failed_delivery(self) -> None:
        """La distinción entera: `not_delivered` es "salimos y no pudimos"; esto nunca salió."""
        assert D_CANCELLED != DELIVERY_NOT_DELIVERED


class FakeRepo:
    """Lo mínimo para probar el guard de transiciones."""

    def __init__(self, delivery: OrderDelivery) -> None:
        self._delivery = delivery

    async def get_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID
    ) -> OrderDelivery:
        return self._delivery


def _delivery(status: str) -> OrderDelivery:
    return OrderDelivery(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        branch_id=uuid.uuid4(),
        order_id=uuid.uuid4(),
        address_text="Calle 1",
        delivery_status=status,
    )


class TestNothingLeavesATerminalState:
    @pytest.mark.asyncio
    async def test_a_cancelled_delivery_cannot_be_resolved_again(self) -> None:
        """Reabrirla dejaría dos desenlaces para un mismo hecho."""
        delivery = _delivery(D_CANCELLED)
        service = DeliveryService(FakeRepo(delivery))  # type: ignore[arg-type]

        with pytest.raises(ConflictError, match="ya está resuelta"):
            await service.mark_delivered(TENANT, delivery.id, delivered=False)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_a_cancelled_delivery_cannot_be_marked_delivered(self) -> None:
        delivery = _delivery(D_CANCELLED)
        service = DeliveryService(FakeRepo(delivery))  # type: ignore[arg-type]

        with pytest.raises(ConflictError):
            await service.mark_delivered(TENANT, delivery.id, delivered=True)  # type: ignore[arg-type]


async def _session_with_delivery(client: AsyncClient, status: str) -> uuid.UUID:
    """Un turno abierto con una entrega en el estado dado. Devuelve el id de la sesión."""
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)
    session_id = await seed_open_cash_session(branch_id)
    await seed_delivery_ready(branch_id)

    resp = await client.post(
        "/storefront/orders",
        json={
            "customer": {"name": "Ana", "phone": "3001234567"},
            "fulfillment": {"type": "delivery", "addressText": "Calle 1 #2-3"},
            "lines": [{"variantId": str(seeded.variant_id), "quantity": 1}],
        },
    )
    assert resp.status_code == 201, resp.text

    async with SessionFactory() as s:
        delivery = (
            await s.execute(select(OrderDeliveryModel))
        ).scalars().one()
        delivery.delivery_status = status
        await s.commit()
    return session_id


class TestWhatACancelledDeliveryStopsBlocking:
    async def test_it_does_not_block_the_cash_close(self, client: AsyncClient) -> None:
        from restaurante.modules.cash.infrastructure.repositories import (
            SqlAlchemyCashRepository,
        )

        session_id = await _session_with_delivery(client, D_CANCELLED)

        async with SessionFactory() as s:
            from tests.modules.messaging.conftest import demo_tenant_id

            unresolved = await SqlAlchemyCashRepository(s).unresolved_deliveries(
                await demo_tenant_id(), session_id
            )

        assert unresolved == []

    async def test_a_pending_delivery_still_blocks_it(self, client: AsyncClient) -> None:
        """El control: sin esto, el test de arriba pasaría aunque la consulta estuviera rota."""
        from restaurante.modules.cash.infrastructure.repositories import (
            SqlAlchemyCashRepository,
        )

        session_id = await _session_with_delivery(client, "pending")

        async with SessionFactory() as s:
            from tests.modules.messaging.conftest import demo_tenant_id

            unresolved = await SqlAlchemyCashRepository(s).unresolved_deliveries(
                await demo_tenant_id(), session_id
            )

        assert len(unresolved) == 1

    async def test_it_does_not_appear_in_the_pending_summary(
        self, client: AsyncClient
    ) -> None:
        from restaurante.modules.reports.infrastructure.repositories import (
            SqlAlchemyReportsRepository,
        )
        from tests.modules.messaging.conftest import demo_tenant_id

        session_id = await _session_with_delivery(client, D_CANCELLED)

        async with SessionFactory() as s:
            count = await SqlAlchemyReportsRepository(s).undelivered_deliveries_for_session(
                await demo_tenant_id(), session_id
            )

        assert count == 0
