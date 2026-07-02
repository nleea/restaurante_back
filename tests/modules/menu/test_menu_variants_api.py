"""Integration tests for the Menu product-variants API (sellable SKUs)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.identity.infrastructure.models import UserModel
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


async def _create_product(client: AsyncClient, headers: dict[str, str]) -> str:
    cat = await client.post("/menu/categories", headers=headers, json={"name": "Burgers"})
    product = await client.post(
        "/menu/products",
        headers=headers,
        json={"category_id": cat.json()["id"], "name": "Classic"},
    )
    return str(product.json()["id"])


async def _create_option(
    client: AsyncClient, headers: dict[str, str], product_id: str, extra_price: str
) -> str:
    group = await client.post(
        f"/menu/products/{product_id}/variant-groups",
        headers=headers,
        json={"name": "Size"},
    )
    option = await client.post(
        f"/menu/variant-groups/{group.json()['id']}/options",
        headers=headers,
        json={"name": "Large", "extra_price": extra_price},
    )
    return str(option.json()["id"])


async def test_create_plain_variant_has_zero_extra_price(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    product_id = await _create_product(client, headers)

    resp = await client.post(
        f"/menu/products/{product_id}/variants",
        headers=headers,
        json={"name": "Estándar"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Estándar"
    assert body["is_active"] is True
    assert body["extra_price"] == "0.00"

    listing = await client.get(f"/menu/products/{product_id}/variants", headers=headers)
    assert listing.status_code == 200
    assert [v["id"] for v in listing.json()] == [body["id"]]


async def test_create_composed_variant_sums_extra_price(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    product_id = await _create_product(client, headers)
    option_id = await _create_option(client, headers, product_id, "3500")

    resp = await client.post(
        f"/menu/products/{product_id}/variants",
        headers=headers,
        json={"name": "Grande", "variant_option_ids": [option_id]},
    )

    assert resp.status_code == 201
    assert resp.json()["extra_price"] == "3500.00"


async def test_rejects_foreign_option(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    product_a = await _create_product(client, headers)
    # An option belonging to a different product.
    cat = await client.post("/menu/categories", headers=headers, json={"name": "Pizza"})
    product_b = (
        await client.post(
            "/menu/products",
            headers=headers,
            json={"category_id": cat.json()["id"], "name": "Margherita"},
        )
    ).json()["id"]
    foreign_option = await _create_option(client, headers, str(product_b), "1000")

    resp = await client.post(
        f"/menu/products/{product_a}/variants",
        headers=headers,
        json={"name": "X", "variant_option_ids": [foreign_option]},
    )
    assert resp.status_code == 422

    listing = await client.get(f"/menu/products/{product_a}/variants", headers=headers)
    assert listing.json() == []


async def test_update_and_delete_variant(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    product_id = await _create_product(client, headers)
    variant_id = (
        await client.post(
            f"/menu/products/{product_id}/variants",
            headers=headers,
            json={"name": "Estándar"},
        )
    ).json()["id"]

    patched = await client.patch(
        f"/menu/variants/{variant_id}",
        headers=headers,
        json={"name": "Sencilla", "is_active": False},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Sencilla"
    assert patched.json()["is_active"] is False

    deleted = await client.delete(f"/menu/variants/{variant_id}", headers=headers)
    assert deleted.status_code == 204
    listing = await client.get(f"/menu/products/{product_id}/variants", headers=headers)
    assert listing.json() == []


async def test_create_requires_manage(client: AsyncClient) -> None:
    await _assign_role("cashier")  # has menu.read, not menu.manage
    headers = await _login(client)
    # The manage gate runs before the handler, so the product need not exist.
    write = await client.post(
        f"/menu/products/{uuid.uuid4()}/variants",
        headers=headers,
        json={"name": "Nope"},
    )
    assert write.status_code == 403
