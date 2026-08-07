"""Integration tests for the Recipes API (ingredients + BOM + RBAC + tenancy)."""

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
from restaurante.modules.kitchen.infrastructure.models import KitchenStationModel
from restaurante.modules.menu.infrastructure.models import (
    CategoryModel,
    ProductModel,
    ProductVariantModel,
)
from restaurante.modules.recipes.domain.entities import Ingredient
from restaurante.modules.recipes.infrastructure.repositories import (
    SqlAlchemyRecipesRepository,
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


async def _create_unit(abbr: str = "g") -> uuid.UUID:
    async with SessionFactory() as session:
        unit = UnitOfMeasureModel(name="gram", abbreviation=abbr)
        session.add(unit)
        await session.commit()
        await session.refresh(unit)
        return unit.id


async def _create_variant(
    name: str = "Classic - L", *, is_active: bool = False
) -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        category = CategoryModel(tenant_id=tenant_id, name="Burgers")
        session.add(category)
        await session.flush()
        product = ProductModel(
            tenant_id=tenant_id, category_id=category.id, name="Classic Burger"
        )
        session.add(product)
        await session.flush()
        # Default: born inactive (like a real new variant), which keeps BOM edits —
        # including deleting the last item — unguarded. Pass is_active=True to
        # exercise the active-variant guards.
        variant = ProductVariantModel(
            tenant_id=tenant_id, product_id=product.id, name=name, is_active=is_active
        )
        session.add(variant)
        await session.commit()
        await session.refresh(variant)
        return variant.id


async def _create_ingredient(unit_id: uuid.UUID, name: str = "Beef") -> uuid.UUID:
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        repo = SqlAlchemyRecipesRepository(session)
        ingredient = await repo.create_ingredient(
            Ingredient(tenant_id=tenant_id, name=name, unit_of_measure_id=unit_id)
        )
        return ingredient.id


# --- Ingredients ------------------------------------------------------------
async def test_ingredient_crud(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()

    created = await client.post(
        "/recipes/ingredients",
        headers=headers,
        json={"name": "Tomato", "unit_of_measure_id": str(unit_id)},
    )
    assert created.status_code == 201, created.text
    ingredient_id = created.json()["id"]

    listing = await client.get("/recipes/ingredients", headers=headers)
    assert any(i["id"] == ingredient_id for i in listing.json())

    deactivated = await client.delete(
        f"/recipes/ingredients/{ingredient_id}", headers=headers
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False


async def test_ingredient_category_round_trip(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()

    # Absent category stays null.
    plain = await client.post(
        "/recipes/ingredients",
        headers=headers,
        json={"name": "Cebolla", "unit_of_measure_id": str(unit_id)},
    )
    assert plain.status_code == 201
    assert plain.json()["category"] is None

    # Category is trimmed on create and survives list reads.
    created = await client.post(
        "/recipes/ingredients",
        headers=headers,
        json={"name": "Churrasco", "unit_of_measure_id": str(unit_id), "category": "  Carnes  "},
    )
    assert created.status_code == 201
    assert created.json()["category"] == "Carnes"
    ingredient_id = created.json()["id"]

    listing = await client.get("/recipes/ingredients", headers=headers)
    row = next(i for i in listing.json() if i["id"] == ingredient_id)
    assert row["category"] == "Carnes"

    # PATCH updates it.
    patched = await client.patch(
        f"/recipes/ingredients/{ingredient_id}",
        headers=headers,
        json={"category": "Proteínas"},
    )
    assert patched.status_code == 200
    assert patched.json()["category"] == "Proteínas"


async def test_ingredient_is_customer_removable_defaults_true(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()

    created = await client.post(
        "/recipes/ingredients",
        headers=headers,
        json={"name": "Tomate", "unit_of_measure_id": str(unit_id)},
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_customer_removable"] is True


async def test_ingredient_is_customer_removable_set_false_and_toggle(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()

    # Born non-removable (e.g. salt/oil), and it round-trips on retrieve + list.
    created = await client.post(
        "/recipes/ingredients",
        headers=headers,
        json={
            "name": "Sal",
            "unit_of_measure_id": str(unit_id),
            "is_customer_removable": False,
        },
    )
    assert created.status_code == 201
    assert created.json()["is_customer_removable"] is False
    ingredient_id = created.json()["id"]

    fetched = await client.get(
        f"/recipes/ingredients/{ingredient_id}", headers=headers
    )
    assert fetched.json()["is_customer_removable"] is False

    listing = await client.get("/recipes/ingredients", headers=headers)
    row = next(i for i in listing.json() if i["id"] == ingredient_id)
    assert row["is_customer_removable"] is False

    # PATCH toggles it back on.
    patched = await client.patch(
        f"/recipes/ingredients/{ingredient_id}",
        headers=headers,
        json={"is_customer_removable": True},
    )
    assert patched.status_code == 200
    assert patched.json()["is_customer_removable"] is True


async def test_ingredient_unknown_unit_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    resp = await client.post(
        "/recipes/ingredients",
        headers=headers,
        json={"name": "Ghost", "unit_of_measure_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


async def _create_station(name: str = "Parrilla") -> uuid.UUID:
    """A kitchen station on its own branch, to hang an insumo's default on."""
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as session:
        branch = BranchModel(
            tenant_id=tenant_id,
            code=f"K{uuid.uuid4().hex[:4]}",
            name="K",
            is_active=True,
        )
        session.add(branch)
        await session.flush()
        station = KitchenStationModel(
            tenant_id=tenant_id, branch_id=branch.id, name=name
        )
        session.add(station)
        await session.commit()
        await session.refresh(station)
        return station.id


async def test_ingredient_default_station_round_trip(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()
    station_id = await _create_station()

    created = await client.post(
        "/recipes/ingredients",
        headers=headers,
        json={
            "name": "Carne",
            "unit_of_measure_id": str(unit_id),
            "default_station_id": str(station_id),
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["default_station_id"] == str(station_id)
    ingredient_id = created.json()["id"]

    fetched = await client.get(f"/recipes/ingredients/{ingredient_id}", headers=headers)
    assert fetched.json()["default_station_id"] == str(station_id)

    listing = await client.get("/recipes/ingredients", headers=headers)
    row = next(i for i in listing.json() if i["id"] == ingredient_id)
    assert row["default_station_id"] == str(station_id)


async def test_ingredient_default_station_defaults_null(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()

    created = await client.post(
        "/recipes/ingredients",
        headers=headers,
        json={"name": "Tomate", "unit_of_measure_id": str(unit_id)},
    )
    assert created.status_code == 201
    assert created.json()["default_station_id"] is None


async def test_ingredient_default_station_can_be_cleared(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()
    station_id = await _create_station()

    created = await client.post(
        "/recipes/ingredients",
        headers=headers,
        json={
            "name": "Tocineta",
            "unit_of_measure_id": str(unit_id),
            "default_station_id": str(station_id),
        },
    )
    ingredient_id = created.json()["id"]

    # An explicit null clears it; the field is only validated when it carries a value.
    cleared = await client.patch(
        f"/recipes/ingredients/{ingredient_id}",
        headers=headers,
        json={"default_station_id": None},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["default_station_id"] is None


async def test_ingredient_patch_without_station_leaves_it_untouched(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()
    station_id = await _create_station()

    created = await client.post(
        "/recipes/ingredients",
        headers=headers,
        json={
            "name": "Queso",
            "unit_of_measure_id": str(unit_id),
            "default_station_id": str(station_id),
        },
    )
    ingredient_id = created.json()["id"]

    # Omitting the field is not the same as sending null: the station survives.
    patched = await client.patch(
        f"/recipes/ingredients/{ingredient_id}",
        headers=headers,
        json={"category": "Lácteos"},
    )
    assert patched.status_code == 200
    assert patched.json()["default_station_id"] == str(station_id)


async def test_ingredient_unknown_station_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()

    created = await client.post(
        "/recipes/ingredients",
        headers=headers,
        json={
            "name": "Fantasma",
            "unit_of_measure_id": str(unit_id),
            "default_station_id": str(uuid.uuid4()),
        },
    )
    assert created.status_code == 404
    assert created.json()["code"] == "not_found"


async def test_ingredient_patch_unknown_station_404_leaves_it_unchanged(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()
    station_id = await _create_station()

    created = await client.post(
        "/recipes/ingredients",
        headers=headers,
        json={
            "name": "Cebolla",
            "unit_of_measure_id": str(unit_id),
            "default_station_id": str(station_id),
        },
    )
    ingredient_id = created.json()["id"]

    rejected = await client.patch(
        f"/recipes/ingredients/{ingredient_id}",
        headers=headers,
        json={"default_station_id": str(uuid.uuid4())},
    )
    assert rejected.status_code == 404

    fetched = await client.get(f"/recipes/ingredients/{ingredient_id}", headers=headers)
    assert fetched.json()["default_station_id"] == str(station_id)


async def test_deleting_a_station_keeps_its_ingredients(client: AsyncClient) -> None:
    """`ON DELETE SET NULL`: kitchen config is never held hostage by insumos."""
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()
    station_id = await _create_station()

    created = await client.post(
        "/recipes/ingredients",
        headers=headers,
        json={
            "name": "Chorizo",
            "unit_of_measure_id": str(unit_id),
            "default_station_id": str(station_id),
        },
    )
    ingredient_id = created.json()["id"]

    async with SessionFactory() as session:
        station = (
            await session.execute(
                select(KitchenStationModel).where(KitchenStationModel.id == station_id)
            )
        ).scalar_one()
        await session.delete(station)
        await session.commit()

    survivor = await client.get(
        f"/recipes/ingredients/{ingredient_id}", headers=headers
    )
    assert survivor.status_code == 200
    assert survivor.json()["default_station_id"] is None


# --- BOM --------------------------------------------------------------------
async def test_bom_flow_and_duplicate_conflict(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()
    variant_id = await _create_variant()
    ingredient_id = await _create_ingredient(unit_id)

    add = await client.post(
        f"/recipes/variants/{variant_id}/items",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "quantity": "150",
            "unit_of_measure_id": str(unit_id),
        },
    )
    assert add.status_code == 201, add.text
    item_id = add.json()["id"]

    recipe = await client.get(
        f"/recipes/variants/{variant_id}/items", headers=headers
    )
    assert len(recipe.json()) == 1

    dup = await client.post(
        f"/recipes/variants/{variant_id}/items",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "quantity": "200",
            "unit_of_measure_id": str(unit_id),
        },
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == "conflict"

    updated = await client.patch(
        f"/recipes/items/{item_id}", headers=headers, json={"quantity": "175"}
    )
    assert updated.status_code == 200
    assert Decimal(updated.json()["quantity"]) == Decimal("175")

    removed = await client.delete(f"/recipes/items/{item_id}", headers=headers)
    assert removed.status_code == 204
    assert (
        await client.get(f"/recipes/variants/{variant_id}/items", headers=headers)
    ).json() == []


async def test_bom_non_positive_quantity_422(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()
    variant_id = await _create_variant()
    ingredient_id = await _create_ingredient(unit_id)

    resp = await client.post(
        f"/recipes/variants/{variant_id}/items",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "quantity": "0",
            "unit_of_measure_id": str(unit_id),
        },
    )
    assert resp.status_code == 422


async def test_bom_unknown_variant_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()
    ingredient_id = await _create_ingredient(unit_id)

    resp = await client.post(
        f"/recipes/variants/{uuid.uuid4()}/items",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "quantity": "10",
            "unit_of_measure_id": str(unit_id),
        },
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


# --- Delete-last guard ------------------------------------------------------
async def test_delete_last_item_of_active_variant_blocked(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()
    variant_id = await _create_variant(is_active=True)
    ingredient_id = await _create_ingredient(unit_id)

    add = await client.post(
        f"/recipes/variants/{variant_id}/items",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "quantity": "150",
            "unit_of_measure_id": str(unit_id),
        },
    )
    item_id = add.json()["id"]

    # Removing the only recipe line of an ACTIVE variant is rejected.
    resp = await client.delete(f"/recipes/items/{item_id}", headers=headers)
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"
    # The line is still there.
    remaining = await client.get(
        f"/recipes/variants/{variant_id}/items", headers=headers
    )
    assert len(remaining.json()) == 1


async def test_delete_non_last_item_of_active_variant_ok(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()
    variant_id = await _create_variant(is_active=True)
    beef = await _create_ingredient(unit_id, name="Beef")
    cheese = await _create_ingredient(unit_id, name="Cheese")

    first = await client.post(
        f"/recipes/variants/{variant_id}/items",
        headers=headers,
        json={
            "ingredient_id": str(beef),
            "quantity": "150",
            "unit_of_measure_id": str(unit_id),
        },
    )
    await client.post(
        f"/recipes/variants/{variant_id}/items",
        headers=headers,
        json={
            "ingredient_id": str(cheese),
            "quantity": "20",
            "unit_of_measure_id": str(unit_id),
        },
    )

    # Two lines: deleting one (not the last) is allowed even while active.
    removed = await client.delete(
        f"/recipes/items/{first.json()['id']}", headers=headers
    )
    assert removed.status_code == 204
    remaining = await client.get(
        f"/recipes/variants/{variant_id}/items", headers=headers
    )
    assert len(remaining.json()) == 1


# --- Missing-recipe read ----------------------------------------------------
async def test_missing_recipe_read_lists_active_zero_recipe_variants(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit_id = await _create_unit()

    # A: active, no recipe -> must be listed.
    variant_a = await _create_variant(name="A", is_active=True)
    # B: active, with a recipe -> excluded.
    variant_b = await _create_variant(name="B", is_active=True)
    ingredient_id = await _create_ingredient(unit_id)
    await client.post(
        f"/recipes/variants/{variant_b}/items",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "quantity": "150",
            "unit_of_measure_id": str(unit_id),
        },
    )
    # C: inactive, no recipe -> excluded (not sellable).
    await _create_variant(name="C", is_active=False)

    resp = await client.get("/recipes/variants/missing-recipe", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [v["product_variant_id"] for v in body] == [str(variant_a)]
    assert body[0]["variant_name"] == "A"
    assert body[0]["product_name"] == "Classic Burger"


# --- RBAC -------------------------------------------------------------------
async def test_requires_permission_without_role(client: AsyncClient) -> None:
    headers = await _login(client)  # demo user has no roles
    resp = await client.get("/recipes/ingredients", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


async def test_read_only_role_cannot_write(client: AsyncClient) -> None:
    await _assign_role("cashier")
    headers = await _login(client)
    unit_id = await _create_unit()
    create = await client.post(
        "/recipes/ingredients",
        headers=headers,
        json={"name": "Nope", "unit_of_measure_id": str(unit_id)},
    )
    assert create.status_code == 403


# --- Tenancy ----------------------------------------------------------------
async def test_repository_isolates_by_tenant(setup_db: None) -> None:
    tenant_a, _ = await _demo_ids()
    tenant_b = uuid.uuid4()
    unit_id = await _create_unit()
    async with SessionFactory() as session:
        repo = SqlAlchemyRecipesRepository(session)
        await repo.create_ingredient(
            Ingredient(tenant_id=tenant_a, name="A-only", unit_of_measure_id=unit_id)
        )
        assert await repo.list_ingredients(tenant_b) == []
        assert len(await repo.list_ingredients(tenant_a)) == 1
