"""Tests for dynamic RBAC: resolution, enforcement and live changes."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.identity.application.use_cases.manage_rbac import RbacService
from restaurante.modules.identity.domain.entities import PermissionEffect
from restaurante.modules.identity.infrastructure.cache import RbacPermissionCache
from restaurante.modules.identity.infrastructure.models import UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.shared.cache import get_cache
from restaurante.shared.database import SessionFactory
from restaurante.shared.security.password import Argon2PasswordHasher
from restaurante.shared.tenancy.models import TenantModel
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


def _permission_cache() -> RbacPermissionCache:
    # Wraps the same process-wide cache singleton the app uses.
    return RbacPermissionCache(get_cache(), ttl_seconds=300)


def _service(session: AsyncSession) -> RbacService:
    return RbacService(repo=SqlAlchemyRbacRepository(session), cache=_permission_cache())


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


async def _seed_roles() -> dict[str, uuid.UUID]:
    async with SessionFactory() as session:
        roles = await seed_rbac(session)
        await session.commit()
        return {name: role.id for name, role in roles.items()}


async def _login(client: AsyncClient) -> str:
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    return str(resp.json()["access_token"])


# --- Unit: resolution = (roles ∪ allow) − deny ------------------------------
async def test_effective_codes_union_minus_deny(setup_db: None) -> None:
    tenant_id, user_id = await _demo_ids()
    roles = await _seed_roles()

    async with SessionFactory() as session:
        repo = SqlAlchemyRbacRepository(session)
        # admin role grants everything...
        await repo.assign_user_role(tenant_id, user_id, roles["admin"])
        # ...but we deny one and additionally allow a (redundant) one.
        perms = {p.code: p.id for p in await repo.list_permissions()}
        await repo.set_user_override(
            tenant_id, user_id, perms["orders.cancel"], PermissionEffect.DENY
        )

        codes = await repo.effective_permission_codes(tenant_id, user_id)

    assert "orders.create" in codes  # from admin role
    assert "orders.cancel" not in codes  # removed by deny override


async def test_allow_override_without_role(setup_db: None) -> None:
    tenant_id, user_id = await _demo_ids()
    await _seed_roles()
    async with SessionFactory() as session:
        repo = SqlAlchemyRbacRepository(session)
        perms = {p.code: p.id for p in await repo.list_permissions()}
        await repo.set_user_override(
            tenant_id, user_id, perms["reports.view"], PermissionEffect.ALLOW
        )
        codes = await repo.effective_permission_codes(tenant_id, user_id)
    assert codes == frozenset({"reports.view"})


# --- Integration: enforcement ----------------------------------------------
async def test_protected_endpoint_forbidden_without_permission(
    client: AsyncClient,
) -> None:
    # Demo user has no roles assigned -> no permissions.
    access = await _login(client)
    resp = await client.get(
        "/rbac/permissions", headers={"Authorization": f"Bearer {access}"}
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


async def test_me_reports_permissions(client: AsyncClient) -> None:
    tenant_id, user_id = await _demo_ids()
    roles = await _seed_roles()
    async with SessionFactory() as session:
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles["cashier"]
        )

    access = await _login(client)
    resp = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {access}"}
    )
    assert resp.status_code == 200
    perms = resp.json()["permissions"]
    assert "orders.read" in perms
    assert "rbac.manage" not in perms


async def test_dynamic_override_grants_access_without_relogin(
    client: AsyncClient,
) -> None:
    tenant_id, user_id = await _demo_ids()
    roles = await _seed_roles()
    async with SessionFactory() as session:
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles["cashier"]
        )

    access = await _login(client)
    headers = {"Authorization": f"Bearer {access}"}

    # Cashier cannot manage RBAC (this read also populates the cache).
    assert (await client.get("/rbac/roles", headers=headers)).status_code == 403

    # Grant a per-user override via the service (which invalidates the cache),
    # same token, no re-login.
    async with SessionFactory() as session:
        await _service(session).set_user_override(
            tenant_id, user_id, "rbac.manage", PermissionEffect.ALLOW
        )

    # The very same access token now works -> dynamic even with caching on.
    assert (await client.get("/rbac/roles", headers=headers)).status_code == 200


async def test_admin_can_manage_roles_and_assignments(client: AsyncClient) -> None:
    tenant_id, user_id = await _demo_ids()
    roles = await _seed_roles()
    async with SessionFactory() as session:
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles["admin"]
        )

    access = await _login(client)
    headers = {"Authorization": f"Bearer {access}"}

    # List permissions catalog.
    perms_resp = await client.get("/rbac/permissions", headers=headers)
    assert perms_resp.status_code == 200
    assert any(p["code"] == "orders.create" for p in perms_resp.json())

    # Create a custom role and set its permissions.
    created = await client.post(
        "/rbac/roles", headers=headers, json={"name": "barista", "description": "Coffee"}
    )
    assert created.status_code == 201
    role_id = created.json()["id"]

    put = await client.put(
        f"/rbac/roles/{role_id}/permissions",
        headers=headers,
        json={"permissions": ["orders.read", "orders.create"]},
    )
    assert put.status_code == 200
    assert set(put.json()["permissions"]) == {"orders.read", "orders.create"}

    # Assign the role to the demo user and read back its access.
    assign = await client.post(
        f"/rbac/users/{user_id}/roles/{role_id}", headers=headers
    )
    assert assign.status_code == 204

    access_resp = await client.get(
        f"/rbac/users/{user_id}/access", headers=headers
    )
    assert access_resp.status_code == 200
    role_names = {r["name"] for r in access_resp.json()["roles"]}
    assert {"admin", "barista"} <= role_names


# --- Caching: read-through + invalidation -----------------------------------
async def test_me_populates_permission_cache(client: AsyncClient) -> None:
    tenant_id, user_id = await _demo_ids()
    roles = await _seed_roles()
    async with SessionFactory() as session:
        await _service(session).assign_user_role(tenant_id, user_id, roles["cashier"])

    cache = _permission_cache()
    assert await cache.get_codes(tenant_id, user_id) is None  # cold

    access = await _login(client)
    await client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})

    cached = await cache.get_codes(tenant_id, user_id)
    assert cached is not None and "orders.read" in cached  # warmed by the read


async def test_user_change_invalidates_cache(client: AsyncClient) -> None:
    tenant_id, user_id = await _demo_ids()
    roles = await _seed_roles()
    async with SessionFactory() as session:
        await _service(session).assign_user_role(tenant_id, user_id, roles["cashier"])

    access = await _login(client)
    await client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    cache = _permission_cache()
    assert await cache.get_codes(tenant_id, user_id) is not None  # warm

    async with SessionFactory() as session:
        await _service(session).set_user_override(
            tenant_id, user_id, "reports.view", PermissionEffect.ALLOW
        )

    assert await cache.get_codes(tenant_id, user_id) is None  # invalidated


async def test_role_permission_change_invalidates_members(client: AsyncClient) -> None:
    tenant_id, user_id = await _demo_ids()
    roles = await _seed_roles()
    async with SessionFactory() as session:
        await _service(session).assign_user_role(tenant_id, user_id, roles["waiter"])

    access = await _login(client)
    await client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    cache = _permission_cache()
    assert await cache.get_codes(tenant_id, user_id) is not None  # warm

    # Changing the role's permissions must fan out invalidation to its members.
    async with SessionFactory() as session:
        await _service(session).add_role_permission(
            tenant_id, roles["waiter"], "reports.view"
        )

    assert await cache.get_codes(tenant_id, user_id) is None


# --- Users listing for RBAC management --------------------------------------
async def test_admin_lists_tenant_users(client: AsyncClient) -> None:
    tenant_id, user_id = await _demo_ids()
    roles = await _seed_roles()
    async with SessionFactory() as session:
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles["admin"]
        )

    access = await _login(client)
    resp = await client.get(
        "/rbac/users", headers={"Authorization": f"Bearer {access}"}
    )
    assert resp.status_code == 200
    users = resp.json()
    me = next(u for u in users if u["email"] == TEST_EMAIL)
    assert me["name"] == "Demo Administrator"
    assert me["is_active"] is True
    assert set(me) >= {"id", "email", "name", "username", "is_active", "last_login_at"}


async def test_list_users_forbidden_without_permission(client: AsyncClient) -> None:
    # Demo user has no roles assigned -> no rbac.manage.
    access = await _login(client)
    resp = await client.get(
        "/rbac/users", headers={"Authorization": f"Bearer {access}"}
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


async def test_list_users_is_tenant_isolated(client: AsyncClient) -> None:
    tenant_id, user_id = await _demo_ids()
    roles = await _seed_roles()
    hasher = Argon2PasswordHasher()
    async with SessionFactory() as session:
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles["admin"]
        )
        # A user belonging to a different tenant must never appear.
        other = TenantModel(slug="other", name="Other", is_active=True)
        session.add(other)
        await session.flush()
        session.add(
            UserModel(
                tenant_id=other.id,
                email="boss@other.com",
                hashed_password=hasher.hash("whatever-123"),
                name="Other Boss",
                is_active=True,
            )
        )
        await session.commit()

    access = await _login(client)
    resp = await client.get(
        "/rbac/users", headers={"Authorization": f"Bearer {access}"}
    )
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert TEST_EMAIL in emails
    assert "boss@other.com" not in emails


async def test_unknown_permission_code_returns_404(client: AsyncClient) -> None:
    tenant_id, user_id = await _demo_ids()
    roles = await _seed_roles()
    async with SessionFactory() as session:
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles["admin"]
        )

    access = await _login(client)
    headers = {"Authorization": f"Bearer {access}"}
    resp = await client.put(
        f"/rbac/users/{user_id}/permissions/does.not.exist",
        headers=headers,
        json={"effect": "allow"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"
