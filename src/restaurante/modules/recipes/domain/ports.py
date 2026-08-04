"""Ports (interfaces) of the Recipes / BOM module."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Protocol

from restaurante.modules.recipes.domain.entities import (
    Ingredient,
    RecipeCardIngredient,
    RecipeDetail,
    RecipeItem,
    VariantMissingRecipe,
)


class RecipesRepository(Protocol):
    # --- Reference existence checks ----------------------------------------
    async def unit_exists(self, unit_of_measure_id: uuid.UUID) -> bool: ...

    async def station_exists(
        self, tenant_id: uuid.UUID, kitchen_station_id: uuid.UUID
    ) -> bool: ...

    async def variant_exists(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> bool: ...

    async def variant_is_active(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> bool: ...

    # --- Ingredients -------------------------------------------------------
    async def create_ingredient(self, ingredient: Ingredient) -> Ingredient: ...

    async def get_ingredient(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> Ingredient | None: ...

    async def list_ingredients(
        self, tenant_id: uuid.UUID, *, active: bool | None = None
    ) -> list[Ingredient]: ...

    async def update_ingredient(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID, fields: dict[str, Any]
    ) -> Ingredient | None: ...

    async def ingredient_unit_costs(
        self, tenant_id: uuid.UUID
    ) -> dict[uuid.UUID, Decimal]: ...

    # --- Recipe items (BOM) ------------------------------------------------
    async def create_recipe_item(self, item: RecipeItem) -> RecipeItem: ...

    async def get_recipe_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> RecipeItem | None: ...

    async def recipe_item_exists(
        self,
        tenant_id: uuid.UUID,
        product_variant_id: uuid.UUID,
        ingredient_id: uuid.UUID,
    ) -> bool: ...

    async def list_recipe_items(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> list[RecipeItem]: ...

    async def count_recipe_items(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> int: ...

    async def list_active_variants_without_recipe(
        self, tenant_id: uuid.UUID
    ) -> list[VariantMissingRecipe]: ...

    async def update_recipe_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> RecipeItem | None: ...

    async def delete_recipe_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> None: ...

    # --- Recipe details (steps + allergens) ---------------------------------
    async def upsert_recipe_detail(self, detail: RecipeDetail) -> RecipeDetail: ...

    async def get_recipe_detail(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> RecipeDetail | None: ...

    # --- Recipe card (aggregated read for kitchen screens) ------------------
    async def list_bom_resolved(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> list[RecipeCardIngredient]: ...
