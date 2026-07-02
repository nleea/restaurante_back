"""Integration tests for the orders ↔ cash payment integration."""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.identity.infrastructure.models import PersonModel, UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.modules.menu.infrastructure.models import (
    CategoryModel,
    ProductModel,
    ProductVariantModel,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import BranchModel, TenantModel
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


async def _demo_ids() -> tuple[uuid.UUID, uuid.UUID]:
    async with SessionFactory() as session:
        tenant = (
            await session.execute(select(TenantModel).where(TenantModel.slug == "demo"))
        ).scalar_one()
        user = (
            await session.execute(
                select(UserModel).where(UserModel.email == TEST_EMAIL)
            )
        ).scalar_one()
        return tenant.id, user.id


async def _assign_role(role_name: str) -> uuid.UUID:
    tenant_id, user_id = await _demo_ids()
    async with SessionFactory() as session:
        roles = await seed_rbac(session)
        await session.commit()
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles[role_name].id
        )
        return roles[role_name].id


async def _login(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_branch(code: str = "B1") -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        branch = BranchModel(
            tenant_id=tenant_id, code=code, name=f"Branch {code}", is_active=True
        )
        session.add(branch)
        await session.commit()
        await session.refresh(branch)
        return branch.id


async def _create_employee(branch_id: uuid.UUID, email: str = "pay@demo.com") -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    role_id = await _assign_role("admin")
    async with SessionFactory() as session:
        person = PersonModel(first_name="Pat", last_name="Payer")
        session.add(person)
        user = UserModel(
            tenant_id=tenant_id,
            email=email,
            hashed_password="x",
            name="Pat Payer",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        employee = EmployeeModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            person_id=person.id,
            user_id=user.id,
            role_id=role_id,
        )
        session.add(employee)
        await session.commit()
        await session.refresh(employee)
        return employee.id


async def _create_variant() -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        category = CategoryModel(tenant_id=tenant_id, name="Burgers")
        session.add(category)
        await session.flush()
        product = ProductModel(
            tenant_id=tenant_id, category_id=category.id, name="Classic Burger"
        )
        session.add(product)
        await session.flush()
        variant = ProductVariantModel(
            tenant_id=tenant_id, product_id=product.id, name="L", is_active=True
        )
        session.add(variant)
        await session.commit()
        await session.refresh(variant)
        return variant.id


async def _open_order(
    client: AsyncClient, headers: dict[str, str], branch_id: uuid.UUID, employee_id: uuid.UUID
) -> str:
    resp = await client.post(
        "/orders",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "channel": "takeaway",
            "employee_id": str(employee_id),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _open_cash_session(
    client: AsyncClient, headers: dict[str, str], branch_id: uuid.UUID, employee_id: uuid.UUID
) -> str:
    resp = await client.post(
        "/cash/sessions",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "opened_by_employee_id": str(employee_id),
            "opening_amount": "0",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --- Happy path -------------------------------------------------------------
async def test_payment_writes_order_payment_and_cash_movement(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    session_id = await _open_cash_session(client, headers, branch_id, employee_id)
    order_id = await _open_order(client, headers, branch_id, employee_id)

    pay = await client.post(
        f"/orders/{order_id}/payments",
        headers=headers,
        json={"amount": "15000", "method": "cash", "employee_id": str(employee_id)},
    )
    assert pay.status_code == 201, pay.text
    assert pay.json()["cash_session_id"] == session_id

    # order payment listed
    payments = await client.get(f"/orders/{order_id}/payments", headers=headers)
    assert len(payments.json()) == 1

    # a `sale` cash movement landed in the session
    movements = await client.get(
        f"/cash/sessions/{session_id}/movements", headers=headers
    )
    sale = [m for m in movements.json() if m["concept"] == "sale"]
    assert len(sale) == 1
    assert sale[0]["type"] == "in"
    assert sale[0]["reference_id"] == order_id


async def test_cash_payment_reflected_in_arqueo(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    session_id = await _open_cash_session(client, headers, branch_id, employee_id)
    order_id = await _open_order(client, headers, branch_id, employee_id)

    await client.post(
        f"/orders/{order_id}/payments",
        headers=headers,
        json={"amount": "15000", "method": "cash", "employee_id": str(employee_id)},
    )
    # non-cash payment must NOT affect the drawer expectation
    await client.post(
        f"/orders/{order_id}/payments",
        headers=headers,
        json={"amount": "99999", "method": "nequi", "employee_id": str(employee_id)},
    )

    close = await client.post(
        f"/cash/sessions/{session_id}/close",
        headers=headers,
        json={"closed_by_employee_id": str(employee_id), "counted_amount": "15000"},
    )
    assert close.status_code == 200
    assert Decimal(close.json()["expected_amount"]) == Decimal("15000")
    assert Decimal(close.json()["difference"]) == Decimal("0")


# --- Guards -----------------------------------------------------------------
async def test_payment_without_open_session_conflicts(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    order_id = await _open_order(client, headers, branch_id, employee_id)

    resp = await client.post(
        f"/orders/{order_id}/payments",
        headers=headers,
        json={"amount": "1000", "method": "cash", "employee_id": str(employee_id)},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


async def test_payment_on_closed_order_conflicts(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    await _open_cash_session(client, headers, branch_id, employee_id)
    order_id = await _open_order(client, headers, branch_id, employee_id)
    await client.post(f"/orders/{order_id}/close", headers=headers)

    resp = await client.post(
        f"/orders/{order_id}/payments",
        headers=headers,
        json={"amount": "1000", "method": "cash", "employee_id": str(employee_id)},
    )
    assert resp.status_code == 409


async def test_payment_non_positive_amount_422(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    await _open_cash_session(client, headers, branch_id, employee_id)
    order_id = await _open_order(client, headers, branch_id, employee_id)

    resp = await client.post(
        f"/orders/{order_id}/payments",
        headers=headers,
        json={"amount": "0", "method": "cash", "employee_id": str(employee_id)},
    )
    assert resp.status_code == 422


# --- RBAC -------------------------------------------------------------------
async def test_payment_requires_pay_permission(client: AsyncClient) -> None:
    # Demo user has no roles -> lacks orders.pay; the permission dependency
    # rejects before any handler logic runs.
    headers = await _login(client)
    resp = await client.post(
        f"/orders/{uuid.uuid4()}/payments",
        headers=headers,
        json={"amount": "1000", "method": "cash", "employee_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"
