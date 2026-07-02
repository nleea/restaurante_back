"""Integration tests for the Finance API (expense categories + expenses + RBAC)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.finance.domain.entities import ExpenseCategory
from restaurante.modules.finance.infrastructure.repositories import (
    SqlAlchemyFinanceRepository,
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


async def _create_branch_and_employee() -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, _ = await _demo_ids()
    role_id = await _assign_role("admin")
    async with SessionFactory() as session:
        branch = BranchModel(
            tenant_id=tenant_id, code="B1", name="Branch 1", is_active=True
        )
        session.add(branch)
        await session.flush()
        person = PersonModel(first_name="Fred", last_name="Finance")
        session.add(person)
        user = UserModel(
            tenant_id=tenant_id,
            email="fred@demo.com",
            hashed_password="x",
            name="Fred Finance",
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
        await session.refresh(branch)
        await session.refresh(employee)
        return branch.id, employee.id


async def _create_category(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/finance/categories", headers=headers, json={"name": "Utilities"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --- Categories -------------------------------------------------------------
async def test_category_crud(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    category_id = await _create_category(client, headers)

    listing = await client.get("/finance/categories", headers=headers)
    assert any(c["id"] == category_id for c in listing.json())

    upd = await client.patch(
        f"/finance/categories/{category_id}", headers=headers, json={"is_active": False}
    )
    assert upd.status_code == 200
    assert upd.json()["is_active"] is False


# --- Expenses ---------------------------------------------------------------
async def test_record_and_list_expenses(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id, employee_id = await _create_branch_and_employee()
    category_id = await _create_category(client, headers)

    resp = await client.post(
        "/finance/expenses",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "expense_category_id": category_id,
            "description": "Electricity bill",
            "amount": "350000",
            "employee_id": str(employee_id),
        },
    )
    assert resp.status_code == 201, resp.text
    expense_id = resp.json()["id"]

    by_branch = await client.get(
        "/finance/expenses", headers=headers, params={"branch_id": str(branch_id)}
    )
    assert any(e["id"] == expense_id for e in by_branch.json())

    by_cat = await client.get(
        "/finance/expenses", headers=headers, params={"category_id": category_id}
    )
    assert len(by_cat.json()) == 1

    got = await client.get(f"/finance/expenses/{expense_id}", headers=headers)
    assert Decimal(got.json()["amount"]) == Decimal("350000")


async def test_expense_non_positive_422(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id, employee_id = await _create_branch_and_employee()
    category_id = await _create_category(client, headers)
    resp = await client.post(
        "/finance/expenses",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "expense_category_id": category_id,
            "description": "x",
            "amount": "0",
            "employee_id": str(employee_id),
        },
    )
    assert resp.status_code == 422


async def test_expense_unknown_category_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id, employee_id = await _create_branch_and_employee()
    resp = await client.post(
        "/finance/expenses",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "expense_category_id": str(uuid.uuid4()),
            "description": "x",
            "amount": "1000",
            "employee_id": str(employee_id),
        },
    )
    assert resp.status_code == 404


# --- RBAC -------------------------------------------------------------------
async def test_requires_permission_without_role(client: AsyncClient) -> None:
    headers = await _login(client)
    resp = await client.get("/finance/categories", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


# --- Tenancy ----------------------------------------------------------------
async def test_repository_isolates_by_tenant(setup_db: None) -> None:
    tenant_a, _ = await _demo_ids()
    tenant_b = uuid.uuid4()
    async with SessionFactory() as session:
        repo = SqlAlchemyFinanceRepository(session)
        await repo.create_category(
            ExpenseCategory(tenant_id=tenant_a, name="Rent")
        )
        assert await repo.list_categories(tenant_b) == []
        assert len(await repo.list_categories(tenant_a)) == 1
