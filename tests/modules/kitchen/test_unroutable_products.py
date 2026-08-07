"""Qué productos no puede preparar nadie — la lista que hace visible un hueco invisible.

Un producto sin estación se ve en la carta exactamente igual que cualquier otro. Sólo deja de
existir en el instante en que la cocina debería haberlo recibido, con el pedido ya cobrado: fue
así como un plato nuevo se vendió, se cobró y se cerró sin que nadie lo cocinara.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.identity.infrastructure.models import UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.modules.kitchen.infrastructure.models import (
    KitchenStationModel,
    ProductStationModel,
)
from restaurante.modules.kitchen.infrastructure.repositories import (
    SqlAlchemyKitchenRepository,
)
from restaurante.modules.menu.infrastructure.models import (
    CategoryModel,
    ProductModel,
    ProductVariantModel,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import BranchModel, TenantModel
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


async def _tenant_id() -> uuid.UUID:
    async with SessionFactory() as s:
        return (
            await s.execute(select(TenantModel.id).where(TenantModel.slug == "demo"))
        ).scalar_one()


async def _login(client: AsyncClient) -> dict[str, str]:
    tenant_id = await _tenant_id()
    async with SessionFactory() as s:
        user_id = (
            await s.execute(select(UserModel.id).where(UserModel.email == TEST_EMAIL))
        ).scalar_one()
        roles = await seed_rbac(s)
        await s.commit()
        await SqlAlchemyRbacRepository(s).assign_user_role(
            tenant_id, user_id, roles["admin"].id
        )
        await s.commit()
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _product(
    name: str, *, active_variants: int = 0, station: bool = False
) -> uuid.UUID:
    """Un producto con o sin estación, y con N variantes activas."""
    tenant_id = await _tenant_id()
    async with SessionFactory() as s:
        category = CategoryModel(tenant_id=tenant_id, name="Salchipapas")
        s.add(category)
        await s.flush()
        product = ProductModel(
            tenant_id=tenant_id, category_id=category.id, name=name
        )
        s.add(product)
        await s.flush()
        for i in range(active_variants):
            s.add(
                ProductVariantModel(
                    tenant_id=tenant_id,
                    product_id=product.id,
                    name=f"v{i}",
                    is_active=True,
                )
            )
        # Una inactiva siempre, para probar que NO cuenta como "se está vendiendo".
        s.add(
            ProductVariantModel(
                tenant_id=tenant_id,
                product_id=product.id,
                name="inactiva",
                is_active=False,
            )
        )
        if station:
            branch = BranchModel(
                tenant_id=tenant_id, code=f"B-{name[:4]}", name="B", is_active=True
            )
            s.add(branch)
            await s.flush()
            kitchen_station = KitchenStationModel(
                tenant_id=tenant_id, branch_id=branch.id, name=f"Est-{name[:4]}"
            )
            s.add(kitchen_station)
            await s.flush()
            s.add(
                ProductStationModel(
                    tenant_id=tenant_id,
                    product_id=product.id,
                    kitchen_station_id=kitchen_station.id,
                )
            )
        await s.commit()
        return product.id


async def _unroutable() -> list[tuple[str, int]]:
    async with SessionFactory() as s:
        rows = await SqlAlchemyKitchenRepository(s).list_unroutable_products(
            await _tenant_id()
        )
    return [(r.name, r.active_variants) for r in rows]


async def test_a_product_with_a_station_is_not_listed(client: AsyncClient) -> None:
    await _product("Con estación", active_variants=1, station=True)

    assert await _unroutable() == []


async def test_a_product_with_no_station_is_listed(client: AsyncClient) -> None:
    await _product("Big Bang", active_variants=2)

    assert await _unroutable() == [("Big Bang", 2)]


async def test_the_ones_already_selling_come_first(client: AsyncClient) -> None:
    """Sin variantes activas es una ficha a medio crear; con ellas es dinero entrando hoy."""
    await _product("Ficha a medias", active_variants=0)
    await _product("Se está vendiendo", active_variants=3)

    assert await _unroutable() == [("Se está vendiendo", 3), ("Ficha a medias", 0)]


async def test_inactive_variants_do_not_count_as_selling(client: AsyncClient) -> None:
    """`_product` siempre añade una inactiva: no debe inflar el conteo."""
    await _product("Sólo inactivas", active_variants=0)

    assert await _unroutable() == [("Sólo inactivas", 0)]


async def test_the_endpoint_returns_them_with_their_category(
    client: AsyncClient,
) -> None:
    headers = await _login(client)
    await _product("Big Bang", active_variants=1)

    resp = await client.get("/kitchen/products/unroutable", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "Big Bang"
    assert body[0]["active_variants"] == 1
    # La categoría, para poder encontrarlo en la carta sin buscar a ciegas.
    assert body[0]["category_name"] == "Salchipapas"


async def test_the_endpoint_needs_only_read_permission(client: AsyncClient) -> None:
    """Saber qué no puede salir de la cocina lo necesita quien mira la carta, no sólo quien
    la configura."""
    resp = await client.get("/kitchen/products/unroutable")

    assert resp.status_code in (401, 403)


async def test_an_already_active_product_is_not_turned_off(client: AsyncClient) -> None:
    """Los platos que YA se venden sin estación se muestran, no se apagan.

    Apagarlos en un despliegue sacaría platos de la carta sin que nadie lo pida y sin que el
    dueño se entere hasta que un cliente pregunte. Una lista que alguien resuelve en dos minutos
    es más fácil de deshacer que una migración que quita cosas.
    """
    from restaurante.modules.menu.infrastructure.models import ProductVariantModel

    product_id = await _product("La Torre", active_variants=2)

    listed = await _unroutable()

    assert ("La Torre", 2) in listed
    # Y sus variantes siguen activas: la lista informa, no desactiva.
    async with SessionFactory() as s:
        active = (
            await s.execute(
                select(ProductVariantModel.is_active).where(
                    ProductVariantModel.product_id == product_id,
                    ProductVariantModel.is_active.is_(True),
                )
            )
        ).scalars().all()
    assert len(active) == 2
