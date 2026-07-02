"""Recipe details (steps + allergens) and the aggregated recipe card for the KDS."""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient

from tests.modules.recipes.test_recipes_api import (
    _assign_role,
    _create_ingredient,
    _create_unit,
    _create_variant,
    _login,
)

DETAILS = {
    "steps": ["Sellar la carne 3 min por lado", "Tostar el pan", "Montar"],
    "allergens": ["gluten", "dairy"],
    "photo_label": "Hamburguesa clásica",
}


async def test_upsert_and_get_details(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    variant_id = await _create_variant()

    put = await client.put(
        f"/recipes/variants/{variant_id}/details", headers=headers, json=DETAILS
    )
    assert put.status_code == 200, put.text
    assert put.json()["steps"] == DETAILS["steps"]
    assert put.json()["allergens"] == ["gluten", "dairy"]

    # Upsert replaces the previous row (still exactly one per variant).
    put2 = await client.put(
        f"/recipes/variants/{variant_id}/details",
        headers=headers,
        json={"steps": ["Solo un paso"], "allergens": ["vegan"]},
    )
    assert put2.status_code == 200
    assert put2.json()["id"] == put.json()["id"]

    got = await client.get(
        f"/recipes/variants/{variant_id}/details", headers=headers
    )
    assert got.status_code == 200
    assert got.json()["steps"] == ["Solo un paso"]
    assert got.json()["allergens"] == ["vegan"]
    assert got.json()["photo_label"] is None


async def test_unknown_allergen_rejected(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    variant_id = await _create_variant()

    resp = await client.put(
        f"/recipes/variants/{variant_id}/details",
        headers=headers,
        json={"steps": [], "allergens": ["peanuts"]},
    )
    assert resp.status_code == 422

    missing = await client.get(
        f"/recipes/variants/{variant_id}/details", headers=headers
    )
    assert missing.status_code == 404


async def test_recipe_card_aggregates_bom_and_details(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    variant_id = await _create_variant()
    unit_id = await _create_unit()
    ingredient_id = await _create_ingredient(unit_id, name="Beef")

    add = await client.post(
        f"/recipes/variants/{variant_id}/items",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "quantity": "180.000",
            "unit_of_measure_id": str(unit_id),
        },
    )
    assert add.status_code == 201, add.text
    await client.put(
        f"/recipes/variants/{variant_id}/details", headers=headers, json=DETAILS
    )

    card = await client.get(f"/recipes/variants/{variant_id}/card", headers=headers)
    assert card.status_code == 200, card.text
    body = card.json()
    assert len(body["ingredients"]) == 1
    ing = body["ingredients"][0]
    assert ing["name"] == "Beef"
    assert Decimal(ing["quantity"]) == Decimal("180")
    assert ing["unit"] == "g"
    assert body["steps"] == DETAILS["steps"]
    assert body["allergens"] == ["gluten", "dairy"]
    assert body["photo_label"] == "Hamburguesa clásica"


async def test_recipe_card_with_bom_only(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    variant_id = await _create_variant()
    unit_id = await _create_unit()
    ingredient_id = await _create_ingredient(unit_id, name="Cheese")

    await client.post(
        f"/recipes/variants/{variant_id}/items",
        headers=headers,
        json={
            "ingredient_id": str(ingredient_id),
            "quantity": "30.000",
            "unit_of_measure_id": str(unit_id),
        },
    )
    card = await client.get(f"/recipes/variants/{variant_id}/card", headers=headers)
    assert card.status_code == 200
    assert card.json()["steps"] == []
    assert card.json()["allergens"] == []
    assert len(card.json()["ingredients"]) == 1


async def test_recipe_card_not_found_without_bom_or_details(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    variant_id = await _create_variant()

    card = await client.get(f"/recipes/variants/{variant_id}/card", headers=headers)
    assert card.status_code == 404

    unknown = await client.get(
        f"/recipes/variants/{uuid.uuid4()}/card", headers=headers
    )
    assert unknown.status_code == 404


async def test_details_write_requires_manage_permission(client: AsyncClient) -> None:
    # No role assigned: authenticated but unauthorized.
    headers = await _login(client)
    variant_id = uuid.uuid4()
    resp = await client.put(
        f"/recipes/variants/{variant_id}/details",
        headers=headers,
        json={"steps": [], "allergens": []},
    )
    assert resp.status_code == 403
