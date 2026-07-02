"""Integration tests for GET /branches (tenant-scoped, authenticated-only)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import BranchModel, TenantModel
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


async def _demo_tenant_id() -> uuid.UUID:
    async with SessionFactory() as session:
        tenant = (
            await session.execute(select(TenantModel).where(TenantModel.slug == "demo"))
        ).scalar_one()
        return tenant.id


async def _login(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _seed_branches(demo_tenant_id: uuid.UUID) -> None:
    """Seed branches for the demo tenant plus a foreign-tenant branch."""
    async with SessionFactory() as session:
        session.add_all(
            [
                BranchModel(
                    tenant_id=demo_tenant_id,
                    code="C-02",
                    name="Sucursal Centro",
                    is_primary=False,
                    is_active=True,
                ),
                BranchModel(
                    tenant_id=demo_tenant_id,
                    code="C-01",
                    name="Sucursal Principal",
                    is_primary=True,
                    is_active=True,
                ),
                BranchModel(
                    tenant_id=demo_tenant_id,
                    code="C-09",
                    name="Sucursal Cerrada",
                    is_primary=False,
                    is_active=False,
                ),
            ]
        )
        # A different tenant with its own branch, to assert isolation.
        other = TenantModel(slug="other", name="Other", is_active=True)
        session.add(other)
        await session.flush()
        session.add(
            BranchModel(
                tenant_id=other.id,
                code="X-01",
                name="Ajena",
                is_primary=True,
                is_active=True,
            )
        )
        await session.commit()


async def test_lists_active_branches_primary_first(client: AsyncClient) -> None:
    demo_id = await _demo_tenant_id()
    await _seed_branches(demo_id)
    headers = await _login(client)

    resp = await client.get("/branches", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    names = [b["name"] for b in body]
    # Only the two active demo branches, primary first.
    assert names == ["Sucursal Principal", "Sucursal Centro"]
    assert body[0]["is_primary"] is True
    assert {"id", "code", "name", "is_primary"} == set(body[0].keys())


async def test_excludes_inactive_and_foreign_tenant(client: AsyncClient) -> None:
    demo_id = await _demo_tenant_id()
    await _seed_branches(demo_id)
    headers = await _login(client)

    resp = await client.get("/branches", headers=headers)

    codes = [b["code"] for b in resp.json()]
    assert "C-09" not in codes  # inactive excluded
    assert "X-01" not in codes  # other tenant never leaks


async def test_requires_authentication(client: AsyncClient) -> None:
    resp = await client.get("/branches")
    assert resp.status_code == 401
