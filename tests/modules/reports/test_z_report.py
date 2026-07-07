"""Integration test for the per-session Reporte Z aggregation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from httpx import AsyncClient

from restaurante.modules.cash.infrastructure.models import (
    CashMovementModel,
    CashSessionModel,
)
from restaurante.modules.finance.infrastructure.models import (
    ExpenseCategoryModel,
    ExpenseModel,
)
from restaurante.modules.orders.infrastructure.models import (
    OrderModel,
    OrderPaymentModel,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from tests.modules.staff.test_staff_api import (
    _assign_role,
    _create_branch,
    _create_person_and_user,
    _demo_ids,
    _login,
)


async def _employee(tenant_id: uuid.UUID, branch_id: uuid.UUID) -> uuid.UUID:
    role_id = await _assign_role("admin")
    person_id, user_id = await _create_person_and_user("emp-z@demo.com")
    async with SessionFactory() as session:
        emp = EmployeeModel(
            tenant_id=tenant_id, branch_id=branch_id,
            person_id=person_id, user_id=user_id, role_id=role_id,
        )
        session.add(emp)
        await session.commit()
        await session.refresh(emp)
        return emp.id


async def test_z_report_aggregates_session(client: AsyncClient) -> None:
    tenant_id, _ = await _demo_ids()
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    emp_id = await _employee(tenant_id, branch_id)

    opened = datetime(2025, 8, 10, 8, 0, tzinfo=UTC)
    async with SessionFactory() as session:
        cs = CashSessionModel(
            tenant_id=tenant_id, branch_id=branch_id, opened_by_employee_id=emp_id,
            opening_amount=Decimal("200000"), expected_amount=Decimal("280000"),
            counted_amount=Decimal("279000"), difference=Decimal("-1000"),
            status="closed", opened_at=opened,
        )
        session.add(cs)
        await session.flush()

        o1 = OrderModel(
            tenant_id=tenant_id, branch_id=branch_id, channel="dine_in",
            employee_id=emp_id, status="closed", subtotal=Decimal("100000"),
            discount=Decimal("0"), total=Decimal("100000"),
            closed_at=datetime(2025, 8, 10, 12, 30, tzinfo=UTC),
        )
        o2 = OrderModel(
            tenant_id=tenant_id, branch_id=branch_id, channel="delivery",
            employee_id=emp_id, status="closed", subtotal=Decimal("50000"),
            discount=Decimal("5000"), total=Decimal("50000"),
            closed_at=datetime(2025, 8, 10, 12, 45, tzinfo=UTC),
        )
        session.add_all([o1, o2])
        await session.flush()

        session.add_all([
            OrderPaymentModel(
                tenant_id=tenant_id, branch_id=branch_id, order_id=o1.id,
                cash_session_id=cs.id, amount=Decimal("100000"),
                method="Efectivo", employee_id=emp_id,
            ),
            OrderPaymentModel(
                tenant_id=tenant_id, branch_id=branch_id, order_id=o2.id,
                cash_session_id=cs.id, amount=Decimal("45000"),
                method="Nequi", employee_id=emp_id,
            ),
            CashMovementModel(
                tenant_id=tenant_id, branch_id=branch_id, cash_session_id=cs.id,
                type="out", concept="Retiro", amount=Decimal("20000"), method="Efectivo",
            ),
        ])
        await session.commit()
        session_id = cs.id

    resp = await client.get(f"/reports/z/{session_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Arqueo comes straight from the session.
    assert Decimal(body["opening_amount"]) == Decimal("200000")
    assert Decimal(body["expected_amount"]) == Decimal("280000")
    assert Decimal(body["difference"]) == Decimal("-1000")
    assert Decimal(body["withdrawals"]) == Decimal("20000")

    # Sales aggregation.
    channels = {c["channel"]: c for c in body["channels"]}
    assert Decimal(channels["dine_in"]["amount"]) == Decimal("100000")
    assert channels["dine_in"]["tickets"] == 1
    assert Decimal(channels["delivery"]["amount"]) == Decimal("50000")
    assert Decimal(body["gross_sales"]) == Decimal("150000")
    assert body["gross_tickets"] == 2
    assert Decimal(body["discounts"]) == Decimal("5000")
    assert Decimal(body["net_sales"]) == Decimal("145000")

    # Payment mix.
    methods = {p["method"]: Decimal(p["amount"]) for p in body["payments"]}
    assert methods == {"Efectivo": Decimal("100000"), "Nequi": Decimal("45000")}

    # Estimated taxes are flagged; operative summary present.
    assert body["taxes_estimated"] is True
    assert Decimal(body["tax_iva"]) > 0
    assert Decimal(body["avg_ticket"]) == Decimal("72500")
    assert body["peak_hour"] == 12
    assert body["top_server_employee_id"] == str(emp_id)
    # Names are resolved server-side (join to person).
    assert body["cashier_name"] == "Jane Doe"
    assert body["top_server_name"] == "Jane Doe"


async def test_revenue_and_daily_engine(client: AsyncClient) -> None:
    tenant_id, _ = await _demo_ids()
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    emp_id = await _employee(tenant_id, branch_id)

    async with SessionFactory() as session:
        cs = CashSessionModel(
            tenant_id=tenant_id, branch_id=branch_id, opened_by_employee_id=emp_id,
            opening_amount=Decimal("0"), status="closed",
            opened_at=datetime(2025, 8, 10, 8, 0, tzinfo=UTC),
        )
        cat = ExpenseCategoryModel(tenant_id=tenant_id, name="Insumos", is_active=True)
        session.add_all([cs, cat])
        await session.flush()

        o1 = OrderModel(
            tenant_id=tenant_id, branch_id=branch_id, channel="dine_in",
            employee_id=emp_id, status="closed", subtotal=Decimal("100000"),
            discount=Decimal("0"), total=Decimal("100000"),
            closed_at=datetime(2025, 8, 10, 12, 0, tzinfo=UTC),
        )
        o2 = OrderModel(
            tenant_id=tenant_id, branch_id=branch_id, channel="delivery",
            employee_id=emp_id, status="closed", subtotal=Decimal("60000"),
            discount=Decimal("5000"), total=Decimal("60000"),
            closed_at=datetime(2025, 8, 10, 13, 0, tzinfo=UTC),
        )
        # An open order in range must NOT count as revenue.
        o3 = OrderModel(
            tenant_id=tenant_id, branch_id=branch_id, channel="dine_in",
            employee_id=emp_id, status="open", subtotal=Decimal("999"),
            discount=Decimal("0"), total=Decimal("999"),
        )
        session.add_all([o1, o2, o3])
        await session.flush()
        session.add_all([
            OrderPaymentModel(
                tenant_id=tenant_id, branch_id=branch_id, order_id=o1.id,
                cash_session_id=cs.id, amount=Decimal("100000"),
                method="Efectivo", employee_id=emp_id,
            ),
            OrderPaymentModel(
                tenant_id=tenant_id, branch_id=branch_id, order_id=o2.id,
                cash_session_id=cs.id, amount=Decimal("55000"),
                method="Nequi", employee_id=emp_id,
            ),
            ExpenseModel(
                tenant_id=tenant_id, branch_id=branch_id,
                expense_category_id=cat.id, description="Compra",
                amount=Decimal("40000"), employee_id=emp_id,
                incurred_at=datetime(2025, 8, 10, 9, 0, tzinfo=UTC),
            ),
        ])
        await session.commit()

    params = {"branch_id": str(branch_id), "from": "2025-08-01", "to": "2025-08-31"}

    rev = await client.get("/reports/revenue", headers=headers, params=params)
    assert rev.status_code == 200, rev.text
    body = rev.json()
    assert Decimal(body["total"]) == Decimal("160000")
    assert body["tickets"] == 2
    assert Decimal(body["discounts"]) == Decimal("5000")
    assert Decimal(body["net"]) == Decimal("155000")
    channels = {c["channel"]: c for c in body["channels"]}
    assert Decimal(channels["dine_in"]["amount"]) == Decimal("100000")
    assert Decimal(channels["delivery"]["amount"]) == Decimal("60000")
    methods = {p["method"]: Decimal(p["amount"]) for p in body["payments"]}
    assert methods == {"Efectivo": Decimal("100000"), "Nequi": Decimal("55000")}

    daily = await client.get("/reports/daily", headers=headers, params=params)
    assert daily.status_code == 200, daily.text
    days = {d["day"]: d for d in daily.json()}
    assert Decimal(days["2025-08-10"]["income"]) == Decimal("160000")
    assert Decimal(days["2025-08-10"]["expenses"]) == Decimal("40000")


async def test_z_report_unknown_session_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    resp = await client.get(f"/reports/z/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


async def test_z_report_requires_permission(client: AsyncClient) -> None:
    headers = await _login(client)  # demo user has no roles
    resp = await client.get(f"/reports/z/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 403
