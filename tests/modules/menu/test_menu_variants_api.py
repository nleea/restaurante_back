"""Integration tests for the Menu product-variants API (sellable SKUs)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.catalog.infrastructure.models import UnitOfMeasureModel
from restaurante.modules.identity.infrastructure.models import UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.modules.recipes.infrastructure.models import (
    IngredientModel,
    RecipeItemModel,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import TenantModel
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


async def _add_station(product_id: str) -> None:
    """Asigna una estación de cocina al producto, para que sus variantes puedan venderse.

    Es el gemelo de `_add_recipe`: dos configuraciones sin las cuales vender es una promesa que
    el negocio no puede cumplir — una descuenta inventario, la otra lo prepara.
    """
    from restaurante.modules.kitchen.infrastructure.models import (
        KitchenStationModel,
        ProductStationModel,
    )
    from restaurante.shared.tenancy.models import BranchModel

    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        branch = BranchModel(
            tenant_id=tenant_id, code=f"K{uuid.uuid4().hex[:4]}", name="K", is_active=True
        )
        session.add(branch)
        await session.flush()
        station = KitchenStationModel(
            tenant_id=tenant_id, branch_id=branch.id, name="Parrilla"
        )
        session.add(station)
        await session.flush()
        session.add(
            ProductStationModel(
                tenant_id=tenant_id,
                product_id=uuid.UUID(product_id),
                kitchen_station_id=station.id,
            )
        )
        await session.commit()


async def _add_recipe(variant_id: str) -> None:
    """Give a variant a single recipe line so it may be put on sale."""
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        unit = UnitOfMeasureModel(name="unit", abbreviation="und")
        session.add(unit)
        await session.flush()
        ingredient = IngredientModel(
            tenant_id=tenant_id, name="Beef", unit_of_measure_id=unit.id, is_active=True
        )
        session.add(ingredient)
        await session.flush()
        session.add(
            RecipeItemModel(
                tenant_id=tenant_id,
                product_variant_id=uuid.UUID(variant_id),
                ingredient_id=ingredient.id,
                quantity=Decimal("1"),
                unit_of_measure_id=unit.id,
            )
        )
        await session.commit()


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
    # New variants are born inactive: not sellable until they have a recipe.
    assert body["is_active"] is False
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


async def test_activate_without_recipe_blocked_then_ok_with_recipe(
    client: AsyncClient,
) -> None:
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

    # No recipe yet -> activation is rejected, variant stays inactive.
    blocked = await client.patch(
        f"/menu/variants/{variant_id}", headers=headers, json={"is_active": True}
    )
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "validation_error"
    listing = await client.get(
        f"/menu/products/{product_id}/variants", headers=headers
    )
    assert listing.json()[0]["is_active"] is False

    # With a recipe AND a station, activation succeeds.
    await _add_recipe(variant_id)
    await _add_station(product_id)
    ok = await client.patch(
        f"/menu/variants/{variant_id}", headers=headers, json={"is_active": True}
    )
    assert ok.status_code == 200
    assert ok.json()["is_active"] is True


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


# --- Estación de cocina: la otra mitad de "se puede vender" -------------------
# Un plato sin estación no lo prepara nadie. Antes se podía activar igual: se vendía, se cobraba
# y la cocina nunca lo veía — pasó con un plato real, y uno de esos pedidos llegó a cerrarse.
async def test_activation_needs_a_kitchen_station_too(client: AsyncClient) -> None:
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
    await _add_recipe(variant_id)  # la receta ya está; falta la estación

    blocked = await client.patch(
        f"/menu/variants/{variant_id}", headers=headers, json={"is_active": True}
    )

    assert blocked.status_code == 422
    detail = blocked.json()["detail"]
    # El mensaje dice QUÉ falta y DÓNDE se arregla: negarse a secas manda a adivinar.
    assert "estación de cocina" in detail
    assert "nadie lo prepararía" in detail
    listing = await client.get(f"/menu/products/{product_id}/variants", headers=headers)
    assert listing.json()[0]["is_active"] is False


async def test_the_recipe_is_still_named_when_that_is_what_is_missing(
    client: AsyncClient,
) -> None:
    """Con estación pero sin receta, el error sigue hablando de la receta."""
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
    await _add_station(product_id)

    blocked = await client.patch(
        f"/menu/variants/{variant_id}", headers=headers, json={"is_active": True}
    )

    assert blocked.status_code == 422
    assert "receta" in blocked.json()["detail"]


async def test_deactivating_needs_neither(client: AsyncClient) -> None:
    """Sacar algo de la carta nunca puede estar bloqueado."""
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

    resp = await client.patch(
        f"/menu/variants/{variant_id}", headers=headers, json={"is_active": False}
    )

    assert resp.status_code == 200


async def test_removing_the_last_station_is_allowed_and_shows_up(
    client: AsyncClient,
) -> None:
    """Quitar la última estación se permite: reorganizar la cocina no puede exigir deshacer la
    venta primero. La variante activa cae en la lista de "no llegan a la cocina", que es donde
    alguien la ve."""
    from restaurante.modules.kitchen.infrastructure.repositories import (
        SqlAlchemyKitchenRepository,
    )

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
    await _add_recipe(variant_id)
    await _add_station(product_id)
    assert (
        await client.patch(
            f"/menu/variants/{variant_id}", headers=headers, json={"is_active": True}
        )
    ).status_code == 200

    # Se quita la única estación que tenía.
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        from sqlalchemy import delete

        from restaurante.modules.kitchen.infrastructure.models import ProductStationModel

        await session.execute(
            delete(ProductStationModel).where(
                ProductStationModel.product_id == uuid.UUID(product_id)
            )
        )
        await session.commit()

    async with SessionFactory() as session:
        unroutable = await SqlAlchemyKitchenRepository(session).list_unroutable_products(
            tenant_id
        )
    mine = [u for u in unroutable if str(u.product_id) == product_id]
    assert len(mine) == 1
    # Y con su variante activa contada: es lo que lo pone primero en la lista.
    assert mine[0].active_variants == 1
