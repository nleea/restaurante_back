"""Integration tests for POST /rbac/users (provision a tenant user + inline person)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.identity.infrastructure.models import PersonModel, UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import TenantModel
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


async def _seed_roles_and_grant_admin() -> dict[str, uuid.UUID]:
    """Seed base roles and give the demo user `admin` (which holds rbac.manage)."""
    tenant_id, user_id = await _demo_ids()
    async with SessionFactory() as session:
        roles = await seed_rbac(session)
        await session.commit()
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles["admin"].id
        )
        return {name: role.id for name, role in roles.items()}


async def _login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_provisions_user_with_person_and_role(client: AsyncClient) -> None:
    roles = await _seed_roles_and_grant_admin()
    headers = await _login(client, TEST_EMAIL, TEST_PASSWORD)

    resp = await client.post(
        "/rbac/users",
        headers=headers,
        json={
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@demo.com",
            "password": "secret-pass-123",
            "role_id": str(roles["cashier"]),
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "jane@demo.com"
    assert body["name"] == "Jane Doe"
    assert body["is_active"] is True
    assert body["person_id"]

    # Person + user actually persisted and linked.
    async with SessionFactory() as session:
        user = (
            await session.execute(
                select(UserModel).where(UserModel.email == "jane@demo.com")
            )
        ).scalar_one()
        assert str(user.person_id) == body["person_id"]
        person = (
            await session.execute(
                select(PersonModel).where(PersonModel.id == user.person_id)
            )
        ).scalar_one()
        assert (person.first_name, person.last_name) == ("Jane", "Doe")

    # Password was hashed correctly: the new user can log in with it.
    login = await client.post(
        "/auth/login", json={"email": "jane@demo.com", "password": "secret-pass-123"}
    )
    assert login.status_code == 200

    # Initial role was assigned.
    access = await client.get(f"/rbac/users/{body['id']}/access", headers=headers)
    assert access.status_code == 200
    assert [r["id"] for r in access.json()["roles"]] == [str(roles["cashier"])]


async def test_duplicate_email_conflicts(client: AsyncClient) -> None:
    await _seed_roles_and_grant_admin()
    headers = await _login(client, TEST_EMAIL, TEST_PASSWORD)
    payload = {
        "first_name": "Ann",
        "last_name": "Lee",
        "email": "ann@demo.com",
        "password": "secret-pass-123",
    }

    first = await client.post("/rbac/users", headers=headers, json=payload)
    assert first.status_code == 201

    second = await client.post("/rbac/users", headers=headers, json=payload)
    assert second.status_code == 409

    # Only one user/person pair exists for that email.
    async with SessionFactory() as session:
        users = (
            await session.execute(
                select(UserModel).where(UserModel.email == "ann@demo.com")
            )
        ).scalars().all()
        assert len(users) == 1


async def test_requires_rbac_manage(client: AsyncClient) -> None:
    # Seed roles but DO NOT grant the demo user any role → no rbac.manage.
    async with SessionFactory() as session:
        await seed_rbac(session)
        await session.commit()
    headers = await _login(client, TEST_EMAIL, TEST_PASSWORD)

    resp = await client.post(
        "/rbac/users",
        headers=headers,
        json={
            "first_name": "No",
            "last_name": "Access",
            "email": "noaccess@demo.com",
            "password": "secret-pass-123",
        },
    )
    assert resp.status_code == 403

    async with SessionFactory() as session:
        users = (
            await session.execute(
                select(UserModel).where(UserModel.email == "noaccess@demo.com")
            )
        ).scalars().all()
        assert users == []
