"""Per-closed-session operational record (orders + deliveries) beside the Reporte Z.

Service-level (no HTTP/RBAC): seeds a session's orders/deliveries and checks the record
aggregates them, excludes null-session (pre-boundary) rows, and 404s on an unknown session.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.delivery.infrastructure.models import OrderDeliveryModel
from restaurante.modules.orders.infrastructure.models import OrderModel
from restaurante.modules.reports.application.use_cases.reporting import ReportsService
from restaurante.modules.reports.infrastructure.repositories import (
    SqlAlchemyReportsRepository,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from restaurante.shared.domain.errors import NotFoundError
from tests.modules._cash import seed_open_cash_session
from tests.modules.storefront._seed import demo_tenant_id, seed_primary_branch


async def _an_employee(tenant_id: uuid.UUID) -> uuid.UUID:
    async with SessionFactory() as session:
        return (
            await session.execute(
                select(EmployeeModel.id).where(EmployeeModel.tenant_id == tenant_id)
            )
        ).scalars().first()


async def _seed_order(
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    employee_id: uuid.UUID,
    session_id: uuid.UUID | None,
    *,
    delivery: bool = False,
) -> uuid.UUID:
    async with SessionFactory() as session:
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            channel="delivery" if delivery else "takeaway",
            employee_id=employee_id,
            total=Decimal("12000"),
            cash_session_id=session_id,
        )
        session.add(order)
        await session.flush()
        if delivery:
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


async def test_record_aggregates_orders_and_deliveries(client: AsyncClient) -> None:
    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    session_id = await seed_open_cash_session(branch_id)
    emp = await _an_employee(tenant_id)

    o1 = await _seed_order(tenant_id, branch_id, emp, session_id)
    o2 = await _seed_order(tenant_id, branch_id, emp, session_id, delivery=True)
    # A pre-boundary (null-session) order must NOT appear in the record.
    await _seed_order(tenant_id, branch_id, emp, None)

    async with SessionFactory() as session:
        svc = ReportsService(repo=SqlAlchemyReportsRepository(session))
        record = await svc.shift_record(tenant_id, session_id)

    assert {o.id for o in record.orders} == {o1, o2}
    assert [d.order_id for d in record.deliveries] == [o2]


async def test_unknown_session_is_404(client: AsyncClient) -> None:
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        svc = ReportsService(repo=SqlAlchemyReportsRepository(session))
        with pytest.raises(NotFoundError):
            await svc.shift_record(tenant_id, uuid.uuid4())
