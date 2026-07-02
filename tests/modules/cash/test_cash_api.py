"""Integration tests for the Cash API (sessions + movements + arqueo + RBAC)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.cash.domain.entities import CashSession
from restaurante.modules.cash.infrastructure.repositories import (
    SqlAlchemyCashRepository,
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


async def _create_employee(branch_id: uuid.UUID, email: str = "cashier@demo.com") -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    role_id = await _assign_role("admin")
    async with SessionFactory() as session:
        person = PersonModel(first_name="Cathy", last_name="Cashier")
        session.add(person)
        user = UserModel(
            tenant_id=tenant_id,
            email=email,
            hashed_password="x",
            name="Cathy Cashier",
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


async def _open_session(
    client: AsyncClient,
    headers: dict[str, str],
    branch_id: uuid.UUID,
    employee_id: uuid.UUID,
    opening: str = "100000",
) -> str:
    resp = await client.post(
        "/cash/sessions",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "opened_by_employee_id": str(employee_id),
            "opening_amount": opening,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --- Sessions ---------------------------------------------------------------
async def test_open_session_and_second_open_conflicts(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)

    await _open_session(client, headers, branch_id, employee_id)
    dup = await client.post(
        "/cash/sessions",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "opened_by_employee_id": str(employee_id),
            "opening_amount": "50000",
        },
    )
    assert dup.status_code == 409


async def test_open_negative_amount_422(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    resp = await client.post(
        "/cash/sessions",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "opened_by_employee_id": str(employee_id),
            "opening_amount": "-1",
        },
    )
    assert resp.status_code == 422


async def test_open_unknown_employee_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    resp = await client.post(
        "/cash/sessions",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "opened_by_employee_id": str(uuid.uuid4()),
            "opening_amount": "1000",
        },
    )
    assert resp.status_code == 404


async def test_get_open_session_404_when_none(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    resp = await client.get(
        f"/cash/branches/{branch_id}/open-session", headers=headers
    )
    assert resp.status_code == 404


# --- Movements --------------------------------------------------------------
async def test_movements_and_non_positive_422(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    session_id = await _open_session(client, headers, branch_id, employee_id)

    ok = await client.post(
        f"/cash/sessions/{session_id}/movements",
        headers=headers,
        json={"type": "in", "concept": "sale", "amount": "20000", "method": "cash"},
    )
    assert ok.status_code == 201

    bad = await client.post(
        f"/cash/sessions/{session_id}/movements",
        headers=headers,
        json={"type": "in", "concept": "sale", "amount": "0", "method": "cash"},
    )
    assert bad.status_code == 422

    movements = await client.get(
        f"/cash/sessions/{session_id}/movements", headers=headers
    )
    assert len(movements.json()) == 1


# --- Close / reconciliation -------------------------------------------------
async def test_close_reconciliation_cash_only(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    session_id = await _open_session(
        client, headers, branch_id, employee_id, opening="100000"
    )

    # cash in 50000, cash out 20000 -> expected = 100000 + 50000 - 20000 = 130000
    for body in (
        {"type": "in", "concept": "sale", "amount": "50000", "method": "cash"},
        {"type": "out", "concept": "withdrawal", "amount": "20000", "method": "cash"},
        # non-cash payment must NOT affect the drawer expectation
        {"type": "in", "concept": "sale", "amount": "99999", "method": "nequi"},
    ):
        r = await client.post(
            f"/cash/sessions/{session_id}/movements", headers=headers, json=body
        )
        assert r.status_code == 201

    close = await client.post(
        f"/cash/sessions/{session_id}/close",
        headers=headers,
        json={"closed_by_employee_id": str(employee_id), "counted_amount": "130000"},
    )
    assert close.status_code == 200
    body = close.json()
    assert body["status"] == "closed"
    assert Decimal(body["expected_amount"]) == Decimal("130000")
    assert Decimal(body["difference"]) == Decimal("0")
    assert body["closed_at"] is not None

    # closing again conflicts
    again = await client.post(
        f"/cash/sessions/{session_id}/close",
        headers=headers,
        json={"closed_by_employee_id": str(employee_id), "counted_amount": "130000"},
    )
    assert again.status_code == 409


async def test_movement_on_closed_session_conflicts(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    session_id = await _open_session(client, headers, branch_id, employee_id)
    await client.post(
        f"/cash/sessions/{session_id}/close",
        headers=headers,
        json={"closed_by_employee_id": str(employee_id), "counted_amount": "100000"},
    )
    resp = await client.post(
        f"/cash/sessions/{session_id}/movements",
        headers=headers,
        json={"type": "in", "concept": "sale", "amount": "1000", "method": "cash"},
    )
    assert resp.status_code == 409


# --- RBAC -------------------------------------------------------------------
async def test_requires_permission_without_role(client: AsyncClient) -> None:
    headers = await _login(client)
    branch_id = await _create_branch()
    resp = await client.get(
        "/cash/sessions", headers=headers, params={"branch_id": str(branch_id)}
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


# --- Tenancy ----------------------------------------------------------------
async def test_repository_isolates_by_tenant(setup_db: None) -> None:
    tenant_a, _ = await _demo_ids()
    tenant_b = uuid.uuid4()
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    async with SessionFactory() as session:
        repo = SqlAlchemyCashRepository(session)
        await repo.create_session(
            CashSession(
                tenant_id=tenant_a,
                branch_id=branch_id,
                opened_by_employee_id=employee_id,
                opening_amount=Decimal("1000"),
            )
        )
        assert await repo.list_sessions(tenant_b, branch_id) == []
        assert len(await repo.list_sessions(tenant_a, branch_id)) == 1
