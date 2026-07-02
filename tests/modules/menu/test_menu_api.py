"""Integration tests for the Menu API (catalog management + RBAC enforcement)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.identity.infrastructure.models import UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.modules.menu.domain.entities import Category
from restaurante.modules.menu.infrastructure.repositories import (
    SqlAlchemyMenuRepository,
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


async def _assign_role(role_name: str) -> None:
    tenant_id, user_id = await _demo_ids()
    async with SessionFactory() as session:
        roles = await seed_rbac(session)
        await session.commit()
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles[role_name].id
        )


async def _login(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_branch() -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        branch = BranchModel(
            tenant_id=tenant_id, code="B1", name="Branch 1", is_active=True
        )
        session.add(branch)
        await session.commit()
        await session.refresh(branch)
        return branch.id


async def test_category_product_price_flow(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()

    cat = await client.post(
        "/menu/categories", headers=headers, json={"name": "Burgers"}
    )
    assert cat.status_code == 201
    category_id = cat.json()["id"]

    prod = await client.post(
        "/menu/products",
        headers=headers,
        json={"category_id": category_id, "name": "Classic Burger"},
    )
    assert prod.status_code == 201
    product_id = prod.json()["id"]

    price = await client.put(
        f"/menu/products/{product_id}/prices/{branch_id}",
        headers=headers,
        json={"price": "18500.00"},
    )
    assert price.status_code == 200
    assert price.json()["branch_id"] == str(branch_id)

    listing = await client.get(f"/menu/products/{product_id}/prices", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    products = await client.get("/menu/products", headers=headers)
    assert any(p["name"] == "Classic Burger" for p in products.json())


async def test_variants_and_addons(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)

    category_id = (
        await client.post("/menu/categories", headers=headers, json={"name": "Pizza"})
    ).json()["id"]
    product_id = (
        await client.post(
            "/menu/products",
            headers=headers,
            json={"category_id": category_id, "name": "Pepperoni"},
        )
    ).json()["id"]

    group = await client.post(
        f"/menu/products/{product_id}/variant-groups",
        headers=headers,
        json={"name": "Size"},
    )
    assert group.status_code == 201
    group_id = group.json()["id"]

    option = await client.post(
        f"/menu/variant-groups/{group_id}/options",
        headers=headers,
        json={"name": "Large", "extra_price": "5000"},
    )
    assert option.status_code == 201

    addon = await client.post(
        "/menu/addons", headers=headers, json={"name": "Extra cheese", "price": "3000"}
    )
    addon_id = addon.json()["id"]

    attach = await client.post(
        f"/menu/products/{product_id}/addons/{addon_id}", headers=headers
    )
    assert attach.status_code == 204

    product_addons = await client.get(
        f"/menu/products/{product_id}/addons", headers=headers
    )
    assert [a["name"] for a in product_addons.json()] == ["Extra cheese"]


async def test_requires_permission_without_role(client: AsyncClient) -> None:
    # Demo user has no roles -> no menu.read.
    headers = await _login(client)
    resp = await client.get("/menu/categories", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


async def test_read_only_role_cannot_write(client: AsyncClient) -> None:
    await _assign_role("cashier")  # has menu.read, not menu.manage
    headers = await _login(client)

    assert (await client.get("/menu/categories", headers=headers)).status_code == 200
    create = await client.post(
        "/menu/categories", headers=headers, json={"name": "Nope"}
    )
    assert create.status_code == 403


async def test_product_with_unknown_category_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    resp = await client.post(
        "/menu/products",
        headers=headers,
        json={"category_id": str(uuid.uuid4()), "name": "Ghost"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


async def test_delete_category_with_products_conflicts(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    category_id = (
        await client.post("/menu/categories", headers=headers, json={"name": "Drinks"})
    ).json()["id"]
    await client.post(
        "/menu/products",
        headers=headers,
        json={"category_id": category_id, "name": "Cola"},
    )

    resp = await client.delete(f"/menu/categories/{category_id}", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


async def test_repository_isolates_by_tenant(setup_db: None) -> None:
    tenant_a, _ = await _demo_ids()
    tenant_b = uuid.uuid4()
    async with SessionFactory() as session:
        repo = SqlAlchemyMenuRepository(session)
        await repo.create_category(Category(tenant_id=tenant_a, name="A-only"))
        # Another tenant must not see tenant A's categories.
        assert await repo.list_categories(tenant_b) == []
        assert len(await repo.list_categories(tenant_a)) == 1
