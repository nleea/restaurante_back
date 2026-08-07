"""Advisory pre-close pending summary: uncollected orders + undelivered deliveries.

Service-level (no HTTP/RBAC): seeds a session's orders/deliveries directly and checks
the summary, that closed/fiado orders are NOT counted, and that a close is BLOCKED while
any delivery of the session is still unresolved (neither delivered nor not_delivered).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.cash.application.use_cases.manage_cash import CashService
from restaurante.modules.cash.infrastructure.repositories import (
    SqlAlchemyCashRepository,
)
from restaurante.modules.delivery.infrastructure.models import OrderDeliveryModel
from restaurante.modules.orders.infrastructure.models import OrderModel
from restaurante.modules.reports.application.use_cases.reporting import ReportsService
from restaurante.modules.reports.infrastructure.repositories import (
    SqlAlchemyReportsRepository,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from restaurante.shared.domain.errors import ConflictError
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
    session_id: uuid.UUID,
    *,
    status: str = "open",
    total: str = "20000",
    delivery_status: str | None = None,
) -> uuid.UUID:
    async with SessionFactory() as session:
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            channel="delivery" if delivery_status else "takeaway",
            employee_id=employee_id,
            status=status,
            total=Decimal(total),
            cash_session_id=session_id,
        )
        session.add(order)
        await session.flush()
        if delivery_status is not None:
            session.add(
                OrderDeliveryModel(
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    order_id=order.id,
                    address_text="Calle 1 #2-3",
                    delivery_status=delivery_status,
                )
            )
        await session.commit()
        return order.id


async def test_summary_counts_uncollected_and_undelivered(client: AsyncClient) -> None:
    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    session_id = await seed_open_cash_session(branch_id)
    emp = await _an_employee(tenant_id)

    # Two open (uncollected) orders, one of them a still-out delivery; one delivered; one closed.
    await _seed_order(tenant_id, branch_id, emp, session_id, status="open", total="10000")
    await _seed_order(
        tenant_id, branch_id, emp, session_id, status="open", total="15000",
        delivery_status="in_transit",
    )
    await _seed_order(
        tenant_id, branch_id, emp, session_id, status="open", total="8000",
        delivery_status="delivered",
    )
    await _seed_order(tenant_id, branch_id, emp, session_id, status="closed", total="9000")

    async with SessionFactory() as session:
        svc = ReportsService(repo=SqlAlchemyReportsRepository(session))
        summary = await svc.pending_summary(tenant_id, session_id)

    # Uncollected = the 3 open orders (closed one excluded); total 10k+15k+8k = 33k.
    assert summary.uncollected_count == 3
    assert summary.uncollected_total == Decimal("33000")
    # Undelivered = only the in_transit one (delivered is terminal).
    assert summary.undelivered_count == 1


async def test_clean_session_reports_zero(client: AsyncClient) -> None:
    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    session_id = await seed_open_cash_session(branch_id)
    emp = await _an_employee(tenant_id)

    # All resolved: a closed order and a delivered delivery.
    await _seed_order(tenant_id, branch_id, emp, session_id, status="closed")
    await _seed_order(
        tenant_id, branch_id, emp, session_id, status="closed",
        delivery_status="delivered",
    )

    async with SessionFactory() as session:
        svc = ReportsService(repo=SqlAlchemyReportsRepository(session))
        summary = await svc.pending_summary(tenant_id, session_id)

    assert summary.uncollected_count == 0
    assert summary.uncollected_total == Decimal("0")
    assert summary.undelivered_count == 0


async def test_close_is_blocked_by_a_delivery_still_out(client: AsyncClient) -> None:
    """Sustituye al viejo "force-close is never blocked".

    Un domicilio en la calle puede llevar efectivo encima. Cerrar el turno con eso pendiente
    es justo cómo se pierde el dato que hace cuadrar la caja.
    """
    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    session_id = await seed_open_cash_session(branch_id)
    emp = await _an_employee(tenant_id)
    await _seed_order(
        tenant_id, branch_id, emp, session_id, status="open",
        delivery_status="in_transit",
    )

    async with SessionFactory() as session:
        cash = CashService(repo=SqlAlchemyCashRepository(session))
        with pytest.raises(ConflictError) as excinfo:
            await cash.close_session(
                tenant_id, session_id, emp, counted_amount=Decimal("0")
            )
    # Y dice cuáles, para que el cajero pueda ir a resolverlos.
    assert "sin resolver" in str(excinfo.value)
    assert "in_transit" in str(excinfo.value)


async def test_close_is_blocked_by_a_delivery_that_never_left(
    client: AsyncClient,
) -> None:
    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    session_id = await seed_open_cash_session(branch_id)
    emp = await _an_employee(tenant_id)
    await _seed_order(
        tenant_id, branch_id, emp, session_id, status="open",
        delivery_status="assigned",
    )

    async with SessionFactory() as session:
        cash = CashService(repo=SqlAlchemyCashRepository(session))
        with pytest.raises(ConflictError):
            await cash.close_session(
                tenant_id, session_id, emp, counted_amount=Decimal("0")
            )


async def test_a_not_delivered_delivery_counts_as_resolved(
    client: AsyncClient,
) -> None:
    """La válvula de escape: el que fue, tocó y nadie salió ya está resuelto."""
    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    session_id = await seed_open_cash_session(branch_id)
    emp = await _an_employee(tenant_id)
    await _seed_order(
        tenant_id, branch_id, emp, session_id, status="closed",
        delivery_status="not_delivered",
    )

    async with SessionFactory() as session:
        cash = CashService(repo=SqlAlchemyCashRepository(session))
        closed = await cash.close_session(
            tenant_id, session_id, emp, counted_amount=Decimal("0")
        )
    assert closed.status == "closed"


async def test_uncollected_orders_alone_do_not_block_the_close(
    client: AsyncClient,
) -> None:
    """Los pedidos sin cobrar siguen siendo informativos: nunca bloquearon y siguen igual."""
    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    session_id = await seed_open_cash_session(branch_id)
    emp = await _an_employee(tenant_id)
    await _seed_order(tenant_id, branch_id, emp, session_id, status="open")

    async with SessionFactory() as session:
        cash = CashService(repo=SqlAlchemyCashRepository(session))
        closed = await cash.close_session(
            tenant_id, session_id, emp, counted_amount=Decimal("0")
        )
    assert closed.status == "closed"
