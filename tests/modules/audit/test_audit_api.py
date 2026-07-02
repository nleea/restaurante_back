"""Integration tests for the Audit query API (read-only log + filters + RBAC)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.identity.infrastructure.models import UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.shared.audit.models import AuditLogModel
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


async def _create_tenant(slug: str = "other") -> uuid.UUID:
    async with SessionFactory() as session:
        tenant = TenantModel(slug=slug, name="Other", is_active=True)
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        return tenant.id


async def _seed_audit(
    tenant_id: uuid.UUID,
    action: str,
    *,
    actor_id: uuid.UUID | None = None,
) -> uuid.UUID:
    async with SessionFactory() as session:
        row = AuditLogModel(
            tenant_id=tenant_id, action=action, actor_id=actor_id
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


# --- Listing + filters ------------------------------------------------------
async def test_list_and_filter_by_action_prefix(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    tenant_id, _ = await _demo_ids()
    await _seed_audit(tenant_id, "login.success")
    await _seed_audit(tenant_id, "login.failure")
    await _seed_audit(tenant_id, "orders.create")

    all_entries = await client.get("/audit/logs", headers=headers)
    assert all_entries.status_code == 200
    # at least the 3 seeded (login flow during _login may add more)
    assert len(all_entries.json()) >= 3

    login_only = await client.get(
        "/audit/logs", headers=headers, params={"action": "login"}
    )
    assert all(e["action"].startswith("login") for e in login_only.json())
    assert any(e["action"] == "orders.create" for e in all_entries.json())
    assert not any(e["action"] == "orders.create" for e in login_only.json())


async def test_filter_by_actor(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    tenant_id, _ = await _demo_ids()
    actor = uuid.uuid4()
    await _seed_audit(tenant_id, "orders.pay", actor_id=actor)
    await _seed_audit(tenant_id, "orders.pay", actor_id=uuid.uuid4())

    resp = await client.get(
        "/audit/logs", headers=headers, params={"actor_id": str(actor)}
    )
    assert len(resp.json()) == 1
    assert resp.json()[0]["actor_id"] == str(actor)


async def test_pagination_limit_clamped(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    tenant_id, _ = await _demo_ids()
    for i in range(5):
        await _seed_audit(tenant_id, f"test.event{i}")

    page = await client.get("/audit/logs", headers=headers, params={"limit": 2})
    assert len(page.json()) == 2
    # limit above max is clamped (no error)
    big = await client.get("/audit/logs", headers=headers, params={"limit": 99999})
    assert big.status_code == 200


async def test_get_entry_and_cross_tenant_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    tenant_id, _ = await _demo_ids()
    entry_id = await _seed_audit(tenant_id, "login.success")

    got = await client.get(f"/audit/logs/{entry_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["action"] == "login.success"

    # an entry of another tenant is not visible
    other_tenant = await _create_tenant()
    other = await _seed_audit(other_tenant, "login.success")
    miss = await client.get(f"/audit/logs/{other}", headers=headers)
    assert miss.status_code == 404


async def test_tenant_isolation_in_list(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    tenant_id, _ = await _demo_ids()
    other_tenant = await _create_tenant()
    await _seed_audit(other_tenant, "orders.create")  # other tenant
    listing = await client.get(
        "/audit/logs", headers=headers, params={"action": "orders"}
    )
    # the other tenant's orders.create must not appear
    assert all(e["action"].startswith("orders") for e in listing.json())
    # and none belongs to the other tenant (we can't see tenant_id, but count is 0
    # because this tenant seeded no orders.* here)
    assert listing.json() == []


# --- RBAC -------------------------------------------------------------------
async def test_requires_permission_without_role(client: AsyncClient) -> None:
    headers = await _login(client)
    resp = await client.get("/audit/logs", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"
