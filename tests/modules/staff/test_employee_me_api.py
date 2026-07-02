"""Integration tests for GET /staff/employees/me (authenticated, no staff.read)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

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


async def _make_demo_employee(role_id: uuid.UUID) -> uuid.UUID:
    """Link the demo user to a fresh employee directly (avoids needing staff.manage)."""
    tenant_id, user_id = await _demo_ids()
    async with SessionFactory() as session:
        branch = BranchModel(tenant_id=tenant_id, code="B1", name="Branch 1", is_active=True)
        person = PersonModel(first_name="Demo", last_name="Worker")
        session.add_all([branch, person])
        await session.flush()
        employee = EmployeeModel(
            tenant_id=tenant_id,
            branch_id=branch.id,
            person_id=person.id,
            user_id=user_id,
            role_id=role_id,
            is_active=True,
        )
        session.add(employee)
        await session.commit()
        await session.refresh(employee)
        return employee.id


async def test_resolves_self(client: AsyncClient) -> None:
    role_id = await _assign_role("admin")
    employee_id = await _make_demo_employee(role_id)
    headers = await _login(client)

    resp = await client.get("/staff/employees/me", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(employee_id)
    assert {"id", "branch_id", "role_id", "is_active"} <= set(body.keys())
    assert body["is_active"] is True


async def test_resolves_without_staff_read(client: AsyncClient) -> None:
    # cashier holds orders.* but NOT staff.read.
    role_id = await _assign_role("cashier")
    employee_id = await _make_demo_employee(role_id)
    headers = await _login(client)

    resp = await client.get("/staff/employees/me", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["id"] == str(employee_id)


async def test_404_when_not_an_employee(client: AsyncClient) -> None:
    await _assign_role("cashier")  # logged in, but never linked to an employee
    headers = await _login(client)

    resp = await client.get("/staff/employees/me", headers=headers)
    assert resp.status_code == 404


async def test_401_unauthenticated(client: AsyncClient) -> None:
    resp = await client.get("/staff/employees/me")
    assert resp.status_code == 401
