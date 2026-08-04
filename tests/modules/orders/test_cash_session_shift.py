"""The open cash session as the operating shift: gate + stamp + live-board scoping.

- Order creation (the single choke point ``open_order``, reached here via the public
  storefront) is rejected with ``cash_closed`` (409) when the branch has no open caja,
  and stamps the order with the open session when there is one.
- Live-board list queries (delivery, salón) filter to the branch's OPEN session and
  exclude closed-session and null-session (pre-boundary) rows. Kitchen uses the same
  order→cash_session join.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.cash.infrastructure.models import CashSessionModel
from restaurante.modules.delivery.infrastructure.models import OrderDeliveryModel
from restaurante.modules.delivery.infrastructure.repositories import (
    SqlAlchemyDeliveryRepository,
)
from restaurante.modules.orders.infrastructure.models import OrderModel
from restaurante.modules.orders.infrastructure.repositories import (
    SqlAlchemyOrdersRepository,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from tests.modules._cash import seed_open_cash_session
from tests.modules.storefront._seed import (
    SeededMenu,
    demo_tenant_id,
    seed_menu,
    seed_primary_branch,
)


def _order_payload(seeded: SeededMenu, **over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "customer": {"name": "Ana", "phone": "3001234567"},
        "fulfillment": {"type": "pickup"},
        "paymentMethod": "efectivo",
        "lines": [{"variantId": str(seeded.variant_id), "quantity": 1}],
    }
    payload.update(over)
    return payload


# --- Gate + stamp ----------------------------------------------------------
async def test_order_rejected_when_caja_closed(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)  # no open caja seeded

    resp = await client.post("/storefront/orders", json=_order_payload(seeded))
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "cash_closed"

    async with SessionFactory() as session:
        orders = (await session.execute(select(OrderModel))).scalars().all()
        assert orders == []  # nothing persisted


async def test_order_stamped_with_open_session(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)
    session_id = await seed_open_cash_session(branch_id)

    resp = await client.post("/storefront/orders", json=_order_payload(seeded))
    assert resp.status_code == 201, resp.text
    order_id = uuid.UUID(resp.json()["orderId"])

    async with SessionFactory() as session:
        order = (
            await session.execute(select(OrderModel).where(OrderModel.id == order_id))
        ).scalar_one()
        assert order.cash_session_id == session_id


# --- Scoping helpers -------------------------------------------------------
async def _an_employee(tenant_id: uuid.UUID) -> uuid.UUID:
    async with SessionFactory() as session:
        return (
            await session.execute(
                select(EmployeeModel.id).where(EmployeeModel.tenant_id == tenant_id)
            )
        ).scalars().first()


async def _closed_session(
    tenant_id: uuid.UUID, branch_id: uuid.UUID, employee_id: uuid.UUID
) -> uuid.UUID:
    async with SessionFactory() as session:
        cs = CashSessionModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            opened_by_employee_id=employee_id,
            opening_amount=Decimal("0"),
            status="closed",
        )
        session.add(cs)
        await session.commit()
        await session.refresh(cs)
        return cs.id


async def _seed_order(
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    employee_id: uuid.UUID,
    cash_session_id: uuid.UUID | None,
    *,
    with_delivery: bool = False,
) -> uuid.UUID:
    async with SessionFactory() as session:
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            channel="delivery" if with_delivery else "takeaway",
            employee_id=employee_id,
            cash_session_id=cash_session_id,
        )
        session.add(order)
        await session.flush()
        if with_delivery:
            session.add(
                OrderDeliveryModel(
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    order_id=order.id,
                    address_text="Calle 1 #2-3",
                    delivery_status="pending",
                )
            )
        await session.commit()
        return order.id


# --- Salón scoping ---------------------------------------------------------
async def test_salon_list_scoped_to_open_session(client: AsyncClient) -> None:
    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    open_session = await seed_open_cash_session(branch_id)
    employee_id = await _an_employee(tenant_id)
    closed_session = await _closed_session(tenant_id, branch_id, employee_id)

    open_order = await _seed_order(tenant_id, branch_id, employee_id, open_session)
    await _seed_order(tenant_id, branch_id, employee_id, closed_session)
    await _seed_order(tenant_id, branch_id, employee_id, None)  # pre-boundary row

    async with SessionFactory() as session:
        repo = SqlAlchemyOrdersRepository(session)
        scoped = await repo.list_orders(
            tenant_id, branch_id=branch_id, open_session_only=True
        )
        assert [o.id for o in scoped] == [open_order]
        # Unscoped still sees all three.
        assert len(await repo.list_orders(tenant_id, branch_id=branch_id)) == 3


async def test_salon_list_empty_when_no_open_session(client: AsyncClient) -> None:
    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    session_id = await seed_open_cash_session(branch_id)
    employee_id = await _an_employee(tenant_id)
    await _seed_order(tenant_id, branch_id, employee_id, session_id)

    # Close that session → the branch now has NO open session.
    async with SessionFactory() as session:
        cs = (
            await session.execute(
                select(CashSessionModel).where(CashSessionModel.id == session_id)
            )
        ).scalar_one()
        cs.status = "closed"
        await session.commit()

    async with SessionFactory() as session:
        repo = SqlAlchemyOrdersRepository(session)
        scoped = await repo.list_orders(
            tenant_id, branch_id=branch_id, open_session_only=True
        )
        assert scoped == []


# --- Delivery scoping (the reported bug) -----------------------------------
async def test_deliveries_scoped_to_open_session(client: AsyncClient) -> None:
    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    open_session = await seed_open_cash_session(branch_id)
    employee_id = await _an_employee(tenant_id)
    closed_session = await _closed_session(tenant_id, branch_id, employee_id)

    open_order = await _seed_order(
        tenant_id, branch_id, employee_id, open_session, with_delivery=True
    )
    await _seed_order(
        tenant_id, branch_id, employee_id, closed_session, with_delivery=True
    )
    await _seed_order(tenant_id, branch_id, employee_id, None, with_delivery=True)

    async with SessionFactory() as session:
        repo = SqlAlchemyDeliveryRepository(session)
        scoped = await repo.list_deliveries(
            tenant_id, branch_id, open_session_only=True
        )
        assert [d.order_id for d in scoped] == [open_order]
        # Unscoped (old behaviour) still returns all three.
        assert len(await repo.list_deliveries(tenant_id, branch_id)) == 3
