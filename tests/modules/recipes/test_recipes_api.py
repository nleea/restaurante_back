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


async def _create_unit(abbr: str = "g") -> uuid.UUID:
    async with SessionFactory() as session:
        unit = UnitOfMeasureModel(name="gram", abbreviation=abbr)
        session.add(unit)
        await session.commit()
        await session.refresh(unit)
        return unit.id


async def _create_variant(name: str = "Classic - L") -> uuid.UUID:
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
        variant = ProductVariantModel(
            tenant_id=tenant_id, product_id=product.id, name=name, is_active=True
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
