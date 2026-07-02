"""Integration tests for the Customers API (customers, preferences, fiado, RBAC)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.customers.domain.entities import Customer
from restaurante.modules.customers.infrastructure.repositories import (
    SqlAlchemyCustomersRepository,
)
from restaurante.modules.identity.infrastructure.models import PersonModel, UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
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


async def _create_employee() -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    role_id = await _assign_role("admin")
    async with SessionFactory() as session:
        branch = BranchModel(
            tenant_id=tenant_id, code="B1", name="Branch 1", is_active=True
        )
        session.add(branch)
        await session.flush()
        person = PersonModel(first_name="Eve", last_name="Employee")
        session.add(person)
        user = UserModel(
            tenant_id=tenant_id,
            email="eve@demo.com",
            hashed_password="x",
            name="Eve Employee",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        employee = EmployeeModel(
            tenant_id=tenant_id,
            branch_id=branch.id,
            person_id=person.id,
            user_id=user.id,
            role_id=role_id,
        )
        session.add(employee)
        await session.commit()
        await session.refresh(employee)
        return employee.id


async def _create_customer(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/customers",
        headers=headers,
        json={"first_name": "John", "last_name": "Diner", "phone": "3001234567"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # The create response embeds the person's identity (no separate person lookup).
    assert body["first_name"] == "John"
    assert body["last_name"] == "Diner"
    assert body["phone"] == "3001234567"
    return body["id"]


# --- Customers --------------------------------------------------------------
async def test_create_list_deactivate_customer(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    customer_id = await _create_customer(client, headers)

    listing = await client.get("/customers", headers=headers)
    listed = next(c for c in listing.json() if c["id"] == customer_id)
    # List reads carry the person identity so the directory can show names.
    assert listed["first_name"] == "John"
    assert listed["last_name"] == "Diner"

    got = await client.get(f"/customers/{customer_id}", headers=headers)
    assert got.json()["is_active"] is True
    assert got.json()["first_name"] == "John"
    assert got.json()["phone"] == "3001234567"

    deact = await client.delete(f"/customers/{customer_id}", headers=headers)
    assert deact.status_code == 200
    assert deact.json()["is_active"] is False


async def test_create_customer_unknown_user_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    resp = await client.post(
        "/customers",
        headers=headers,
        json={
            "first_name": "Ann",
            "last_name": "Onymous",
            "user_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 404


# --- Preferences ------------------------------------------------------------
async def test_preferences_flow(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    customer_id = await _create_customer(client, headers)

    pref = await client.post(
        f"/customers/{customer_id}/preferences",
        headers=headers,
        json={"key": "no_onion", "value": "true"},
    )
    assert pref.status_code == 201
    pref_id = pref.json()["id"]

    prefs = await client.get(f"/customers/{customer_id}/preferences", headers=headers)
    assert len(prefs.json()) == 1

    rm = await client.delete(f"/customers/preferences/{pref_id}", headers=headers)
    assert rm.status_code == 204
    assert (
        await client.get(f"/customers/{customer_id}/preferences", headers=headers)
    ).json() == []


# --- Credit (fiado) ---------------------------------------------------------
async def test_credit_partial_then_paid(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    employee_id = await _create_employee()
    customer_id = await _create_customer(client, headers)

    credit = await client.post(
        f"/customers/{customer_id}/credits",
        headers=headers,
        json={"total_amount": "30000"},
    )
    assert credit.status_code == 201
    assert credit.json()["payment_status"] == "pending"
    credit_id = credit.json()["id"]

    p1 = await client.post(
        f"/customers/credits/{credit_id}/payments",
        headers=headers,
        json={"amount": "10000", "method": "transfer", "employee_id": str(employee_id)},
    )
    assert p1.status_code == 201
    assert (
        await client.get(f"/customers/credits/{credit_id}", headers=headers)
    ).json()["payment_status"] == "partial"

    await client.post(
        f"/customers/credits/{credit_id}/payments",
        headers=headers,
        json={"amount": "20000", "method": "nequi", "employee_id": str(employee_id)},
    )
    assert (
        await client.get(f"/customers/credits/{credit_id}", headers=headers)
    ).json()["payment_status"] == "paid"


async def _employee_branch(employee_id: uuid.UUID) -> uuid.UUID:
    async with SessionFactory() as session:
        return (
            await session.execute(
                select(EmployeeModel.branch_id).where(EmployeeModel.id == employee_id)
            )
        ).scalar_one()


async def test_cash_credit_settlement_posts_drawer_movement(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    employee_id = await _create_employee()
    branch_id = await _employee_branch(employee_id)
    customer_id = await _create_customer(client, headers)
    credit_id = (
        await client.post(
            f"/customers/{customer_id}/credits",
            headers=headers,
            json={"total_amount": "30000"},
        )
    ).json()["id"]

    # A cash settlement without an open session is rejected.
    rejected = await client.post(
        f"/customers/credits/{credit_id}/payments",
        headers=headers,
        json={"amount": "10000", "method": "cash", "employee_id": str(employee_id)},
    )
    assert rejected.status_code == 409

    # Open the paying employee's branch session, then the cash settlement posts an `in` movement.
    session_id = (
        await client.post(
            "/cash/sessions",
            headers=headers,
            json={
                "branch_id": str(branch_id),
                "opened_by_employee_id": str(employee_id),
                "opening_amount": "0",
            },
        )
    ).json()["id"]
    paid = await client.post(
        f"/customers/credits/{credit_id}/payments",
        headers=headers,
        json={"amount": "10000", "method": "cash", "employee_id": str(employee_id)},
    )
    assert paid.status_code == 201

    movements = (
        await client.get(f"/cash/sessions/{session_id}/movements", headers=headers)
    ).json()
    fiado = [m for m in movements if m["concept"] == "credit_payment"]
    assert len(fiado) == 1
    assert fiado[0]["type"] == "in"
    assert fiado[0]["reference_id"] == credit_id

    # A non-cash settlement writes no further cash movement.
    await client.post(
        f"/customers/credits/{credit_id}/payments",
        headers=headers,
        json={"amount": "5000", "method": "nequi", "employee_id": str(employee_id)},
    )
    movements2 = (
        await client.get(f"/cash/sessions/{session_id}/movements", headers=headers)
    ).json()
    assert len([m for m in movements2 if m["concept"] == "credit_payment"]) == 1


async def test_credit_non_positive_422(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    customer_id = await _create_customer(client, headers)
    resp = await client.post(
        f"/customers/{customer_id}/credits",
        headers=headers,
        json={"total_amount": "0"},
    )
    assert resp.status_code == 422


# --- RBAC -------------------------------------------------------------------
async def test_requires_permission_without_role(client: AsyncClient) -> None:
    headers = await _login(client)
    resp = await client.get("/customers", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


# --- Tenancy ----------------------------------------------------------------
async def test_repository_isolates_by_tenant(setup_db: None) -> None:
    tenant_a, _ = await _demo_ids()
    tenant_b = uuid.uuid4()
    async with SessionFactory() as session:
        repo = SqlAlchemyCustomersRepository(session)
        await repo.create_customer(
            {"first_name": "Iso", "last_name": "Lated"},
            Customer(tenant_id=tenant_a, person_id=uuid.uuid4()),
        )
        assert await repo.list_customers(tenant_b) == []
        assert len(await repo.list_customers(tenant_a)) == 1
