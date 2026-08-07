"""Public storefront menu read-model: customer-safe, active-only, flag-filtered."""

from __future__ import annotations

from httpx import AsyncClient

from tests.modules.storefront._seed import (
    seed_inactive_noise,
    seed_menu,
    seed_primary_branch,
)


async def test_menu_unauthenticated_lists_active_products(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)
    await seed_inactive_noise(branch_id)

    resp = await client.get("/storefront/menu")
    assert resp.status_code == 200
    body = resp.json()

    category_names = [c["name"] for c in body["categories"]]
    assert "Ceviches" in category_names
    assert "Bebidas" in category_names
    assert "Archivados" not in category_names  # inactive category excluded

    product_names = [p["name"] for p in body["products"]]
    assert product_names == ["Ceviche Mixto"]  # inactive product/category excluded

    product = body["products"][0]
    assert product["categoryId"] == str(seeded.category_id)
    assert product["description"] == "Fresco del día"
    assert product["imageUrl"].endswith("ceviche.png")
    assert product["price"] == "28000.00"
    assert product["variantId"] == str(seeded.variant_id)
    assert product["addons"] == [
        {"id": str(seeded.addon_id), "name": "Extra Limón", "price": "6000.00"}
    ]


async def test_menu_removables_filtered_by_flag(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch()
    await seed_menu(branch_id)

    resp = await client.get("/storefront/menu")
    assert resp.status_code == 200
    product = resp.json()["products"][0]
    # "Cebolla" is customer-removable; "Sal" is a staple (flag false) → absent.
    assert product["removableIngredients"] == ["Cebolla"]


async def test_menu_leaks_no_internal_fields(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch()
    await seed_menu(branch_id)

    resp = await client.get("/storefront/menu")
    assert resp.status_code == 200
    product = resp.json()["products"][0]
    forbidden = {
        "cost",
        "quantity",
        "recipe",
        "recipeItems",
        "ingredients",
        "bom",
        "unitOfMeasureId",
    }
    assert forbidden.isdisjoint(product.keys())
    for addon in product["addons"]:
        assert "cost" not in addon
        assert "quantity" not in addon
