"""Integration tests for the Staff API (workforce management + RBAC + tenancy)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.identity.infrastructure.models import (
    PersonModel,
    UserModel,
)
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.modules.staff.domain.entities import Employee
from restaurante.modules.staff.infrastructure.repositories import (
    SqlAlchemyStaffRepository,
)
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
    """Seed RBAC, assign ``role_name`` to the demo user, return that role's id."""
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


async def _create_person_and_user(email: str) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        person = PersonModel(first_name="Jane", last_name="Doe")
        session.add(person)
        await session.flush()
        user = UserModel(
            tenant_id=tenant_id,
            email=email,
            hashed_password="x",
            name="Jane Doe",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(person)
        await session.refresh(user)
        return person.id, user.id


async def _create_employee(client: AsyncClient, headers: dict[str, str]) -> str:
    branch_id = await _create_branch()
    role_id = await _assign_role("admin")
    person_id, user_id = await _create_person_and_user("jane@demo.com")
    resp = await client.post(
        "/staff/employees",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "person_id": str(person_id),
            "user_id": str(user_id),
            "role_id": str(role_id),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# --- Employees --------------------------------------------------------------
async def test_create_and_list_employee(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    employee_id = await _create_employee(client, headers)

    listing = await client.get("/staff/employees", headers=headers)
    assert listing.status_code == 200
    assert any(e["id"] == employee_id for e in listing.json())

    got = await client.get(f"/staff/employees/{employee_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["is_active"] is True


async def test_duplicate_person_conflicts(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    role_id = await _assign_role("admin")
    person_id, user_id = await _create_person_and_user("a@demo.com")

    first = await client.post(
        "/staff/employees",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "person_id": str(person_id),
            "user_id": str(user_id),
            "role_id": str(role_id),
        },
    )
    assert first.status_code == 201

    _, other_user_id = await _create_person_and_user("b@demo.com")
    dup = await client.post(
        "/staff/employees",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "person_id": str(person_id),  # same person
            "user_id": str(other_user_id),
            "role_id": str(role_id),
        },
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == "conflict"


async def test_unknown_branch_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    role_id = await _assign_role("admin")
    person_id, user_id = await _create_person_and_user("c@demo.com")
    resp = await client.post(
        "/staff/employees",
        headers=headers,
        json={
            "branch_id": str(uuid.uuid4()),
            "person_id": str(person_id),
            "user_id": str(user_id),
            "role_id": str(role_id),
        },
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


async def test_deactivate_employee(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    employee_id = await _create_employee(client, headers)
    resp = await client.delete(f"/staff/employees/{employee_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


# --- Planned shifts ---------------------------------------------------------
async def test_shift_flow_and_time_validation(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    employee_id = await _create_employee(client, headers)

    ok = await client.post(
        f"/staff/employees/{employee_id}/shifts",
        headers=headers,
        json={"shift_date": "2026-07-01", "start_time": "08:00", "end_time": "16:00"},
    )
    assert ok.status_code == 201

    bad = await client.post(
        f"/staff/employees/{employee_id}/shifts",
        headers=headers,
        json={"shift_date": "2026-07-01", "start_time": "16:00", "end_time": "08:00"},
    )
    assert bad.status_code == 422

    shifts = await client.get(
        f"/staff/employees/{employee_id}/shifts", headers=headers
    )
    assert len(shifts.json()) == 1


# --- Attendances ------------------------------------------------------------
async def test_attendance_single_open_invariant(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    employee_id = await _create_employee(client, headers)

    first = await client.post(
        f"/staff/employees/{employee_id}/attendances",
        headers=headers,
        json={"check_in_at": "2026-07-01T08:00:00Z"},
    )
    assert first.status_code == 201
    attendance_id = first.json()["id"]

    second = await client.post(
        f"/staff/employees/{employee_id}/attendances",
        headers=headers,
        json={"check_in_at": "2026-07-01T09:00:00Z"},
    )
    assert second.status_code == 409

    bad_out = await client.patch(
        f"/staff/attendances/{attendance_id}",
        headers=headers,
        json={"check_out_at": "2026-07-01T07:00:00Z"},
    )
    assert bad_out.status_code == 422

    good_out = await client.patch(
        f"/staff/attendances/{attendance_id}",
        headers=headers,
        json={"check_out_at": "2026-07-01T16:00:00Z"},
    )
    assert good_out.status_code == 200
    assert good_out.json()["check_out_at"] is not None


# --- Commissions ------------------------------------------------------------
async def test_commission_positive_amount(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    employee_id = await _create_employee(client, headers)

    ok = await client.post(
        f"/staff/employees/{employee_id}/commissions",
        headers=headers,
        json={"type": "delivery", "amount": "5000.00"},
    )
    assert ok.status_code == 201

    bad = await client.post(
        f"/staff/employees/{employee_id}/commissions",
        headers=headers,
        json={"type": "delivery", "amount": "0"},
    )
    assert bad.status_code == 422

    listing = await client.get(
        f"/staff/employees/{employee_id}/commissions", headers=headers
    )
    assert len(listing.json()) == 1


# --- RBAC -------------------------------------------------------------------
async def test_requires_permission_without_role(client: AsyncClient) -> None:
    headers = await _login(client)  # demo user has no roles
    resp = await client.get("/staff/employees", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


async def test_read_only_role_cannot_write(client: AsyncClient) -> None:
    await _assign_role("cashier")  # has staff.read? verify read works / write blocked
    headers = await _login(client)
    # Read is allowed only if cashier has staff.read; regardless, a write must 403.
    create = await client.post(
        "/staff/employees",
        headers=headers,
        json={
            "branch_id": str(uuid.uuid4()),
            "person_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "role_id": str(uuid.uuid4()),
        },
    )
    assert create.status_code == 403


# --- Tenancy ----------------------------------------------------------------
async def test_repository_isolates_by_tenant(setup_db: None) -> None:
    tenant_a, _ = await _demo_ids()
    tenant_b = uuid.uuid4()
    branch_id = await _create_branch()
    person_id, user_id = await _create_person_and_user("iso@demo.com")
    role_id = await _assign_role("admin")
    async with SessionFactory() as session:
        repo = SqlAlchemyStaffRepository(session)
        await repo.create_employee(
            Employee(
                tenant_id=tenant_a,
                branch_id=branch_id,
                person_id=person_id,
                user_id=user_id,
                role_id=role_id,
            )
        )
        assert await repo.list_employees(tenant_b) == []
        assert len(await repo.list_employees(tenant_a)) == 1
