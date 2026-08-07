"""Application service for the Recipes / BOM module.

Validates domain rules (referenced unit/variant/ingredient exist in scope,
positive quantities, no duplicate ingredient per variant) and delegates
persistence to `RecipesRepository`. Accepts/returns framework-free entities.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from restaurante.modules.recipes.domain.entities import (
    ALLERGEN_KEYS,
    Ingredient,
    IngredientCost,
    RecipeCard,
    RecipeDetail,
    RecipeItem,
    VariantMissingRecipe,
)
from restaurante.modules.recipes.domain.ports import RecipesRepository
from restaurante.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)


class RecipesService:
    def __init__(self, repo: RecipesRepository) -> None:
        self._repo = repo

    # --- internal guards ---------------------------------------------------
    async def _require_ingredient(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> Ingredient:
        ingredient = await self._repo.get_ingredient(tenant_id, ingredient_id)
        if ingredient is None:
            raise NotFoundError(f"Insumo no encontrado: {ingredient_id}")
        return ingredient

    async def _require_unit(self, unit_of_measure_id: uuid.UUID) -> None:
        if not await self._repo.unit_exists(unit_of_measure_id):
            raise NotFoundError(
                f"Unidad de medida no encontrada: {unit_of_measure_id}"
            )

    async def _require_station(
        self, tenant_id: uuid.UUID, kitchen_station_id: uuid.UUID
    ) -> None:
        if not await self._repo.station_exists(tenant_id, kitchen_station_id):
            raise NotFoundError(
                f"Estación de cocina no encontrada: {kitchen_station_id}"
            )

    async def _require_variant(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> None:
        if not await self._repo.variant_exists(tenant_id, product_variant_id):
            raise NotFoundError(
                f"Variante de producto no encontrada: {product_variant_id}"
            )

    async def _require_recipe_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> RecipeItem:
        item = await self._repo.get_recipe_item(tenant_id, item_id)
        if item is None:
            raise NotFoundError(f"Línea de receta no encontrada: {item_id}")
        return item

    # --- Ingredients -------------------------------------------------------
    async def create_ingredient(
        self,
        tenant_id: uuid.UUID,
        name: str,
        unit_of_measure_id: uuid.UUID,
        *,
        category: str | None = None,
        is_customer_removable: bool = True,
        default_station_id: uuid.UUID | None = None,
    ) -> Ingredient:
        await self._require_unit(unit_of_measure_id)
        if default_station_id is not None:
            await self._require_station(tenant_id, default_station_id)
        return await self._repo.create_ingredient(
            Ingredient(
                tenant_id=tenant_id,
                name=name,
                category=category,
                unit_of_measure_id=unit_of_measure_id,
                is_customer_removable=is_customer_removable,
                default_station_id=default_station_id,
            )
        )

    async def list_ingredients(
        self, tenant_id: uuid.UUID, *, active: bool | None = None
    ) -> list[Ingredient]:
        return await self._repo.list_ingredients(tenant_id, active=active)

    async def get_ingredient(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> Ingredient:
        return await self._require_ingredient(tenant_id, ingredient_id)

    async def update_ingredient(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID, fields: dict[str, Any]
    ) -> Ingredient:
        if fields.get("unit_of_measure_id") is not None:
            await self._require_unit(fields["unit_of_measure_id"])
        # `.get() is not None` on purpose: an explicit null clears the station, and
        # clearing must not be validated against a station that no longer exists.
        if fields.get("default_station_id") is not None:
            await self._require_station(tenant_id, fields["default_station_id"])
        updated = await self._repo.update_ingredient(tenant_id, ingredient_id, fields)
        if updated is None:
            raise NotFoundError(f"Insumo no encontrado: {ingredient_id}")
        return updated

    async def deactivate_ingredient(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> Ingredient:
        await self._require_ingredient(tenant_id, ingredient_id)
        updated = await self._repo.update_ingredient(
            tenant_id, ingredient_id, {"is_active": False}
        )
        if updated is None:
            raise NotFoundError(f"Insumo no encontrado: {ingredient_id}")
        return updated

    async def list_ingredient_costs(
        self, tenant_id: uuid.UUID
    ) -> list[IngredientCost]:
        """Per-ingredient unit cost for live menu costing.

        Every ingredient gets an entry; ``unit_cost`` is the moving-average of its
        purchases, or ``None`` when it has no purchase history — unavailable, never
        zero, so the food-cost meter can show an honest partial state.
        """
        costs = await self._repo.ingredient_unit_costs(tenant_id)
        ingredients = await self._repo.list_ingredients(tenant_id)
        return [
            IngredientCost(ingredient_id=i.id, unit_cost=costs.get(i.id))
            for i in ingredients
            if i.id is not None
        ]

    # --- Recipe items (BOM) ------------------------------------------------
    async def add_recipe_item(
        self,
        tenant_id: uuid.UUID,
        product_variant_id: uuid.UUID,
        ingredient_id: uuid.UUID,
        quantity: Decimal,
        unit_of_measure_id: uuid.UUID,
        station_id: uuid.UUID | None = None,
    ) -> RecipeItem:
        await self._require_variant(tenant_id, product_variant_id)
        await self._require_ingredient(tenant_id, ingredient_id)
        await self._require_unit(unit_of_measure_id)
        if station_id is not None:
            await self._require_station(tenant_id, station_id)
        if quantity <= 0:
            raise ValidationError("La cantidad de la receta debe ser positiva.")
        if await self._repo.recipe_item_exists(
            tenant_id, product_variant_id, ingredient_id
        ):
            raise ConflictError(
                "Ese insumo ya forma parte de la receta de la variante."
            )
        return await self._repo.create_recipe_item(
            RecipeItem(
                tenant_id=tenant_id,
                product_variant_id=product_variant_id,
                ingredient_id=ingredient_id,
                quantity=quantity,
                unit_of_measure_id=unit_of_measure_id,
                station_id=station_id,
            )
        )

    async def list_recipe_items(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> list[RecipeItem]:
        await self._require_variant(tenant_id, product_variant_id)
        return await self._repo.list_recipe_items(tenant_id, product_variant_id)

    async def update_recipe_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> RecipeItem:
        await self._require_recipe_item(tenant_id, item_id)
        if "quantity" in fields and fields["quantity"] is not None:
            if fields["quantity"] <= 0:
                raise ValidationError("La cantidad de la receta debe ser positiva.")
        if fields.get("unit_of_measure_id") is not None:
            await self._require_unit(fields["unit_of_measure_id"])
        # Null explícito vuelve al default del insumo, así que sólo se valida con valor.
        if fields.get("station_id") is not None:
            await self._require_station(tenant_id, fields["station_id"])
        updated = await self._repo.update_recipe_item(tenant_id, item_id, fields)
        if updated is None:
            raise NotFoundError(f"Línea de receta no encontrada: {item_id}")
        return updated

    async def delete_recipe_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> None:
        item = await self._require_recipe_item(tenant_id, item_id)
        # Delete-last guard: keep the invariant (active ⇒ ≥1 recipe item) from being
        # broken after activation. Removing the last item of an active variant is
        # blocked; deactivate it first. Non-last items, or items of an inactive
        # variant, delete freely.
        if await self._repo.variant_is_active(tenant_id, item.product_variant_id):
            remaining = await self._repo.count_recipe_items(
                tenant_id, item.product_variant_id
            )
            if remaining <= 1:
                raise ValidationError(
                    "Desactiva la variante antes de quitar su última receta."
                )
        await self._repo.delete_recipe_item(tenant_id, item_id)

    async def list_variants_missing_recipe(
        self, tenant_id: uuid.UUID
    ) -> list[VariantMissingRecipe]:
        """Active (sellable) variants that still have zero recipe items."""
        return await self._repo.list_active_variants_without_recipe(tenant_id)

    # --- Recipe details (steps + allergens) ---------------------------------
    async def upsert_recipe_detail(
        self,
        tenant_id: uuid.UUID,
        product_variant_id: uuid.UUID,
        steps: list[str],
        allergens: list[str],
        photo_label: str | None = None,
    ) -> RecipeDetail:
        await self._require_variant(tenant_id, product_variant_id)
        # The API schema already closes the vocabulary; re-validate here so the rule holds
        # for any caller of the use case, not just the router.
        unknown = [a for a in allergens if a not in ALLERGEN_KEYS]
        if unknown:
            raise ValidationError(f"Alérgenos desconocidos: {', '.join(unknown)}")
        return await self._repo.upsert_recipe_detail(
            RecipeDetail(
                tenant_id=tenant_id,
                product_variant_id=product_variant_id,
                steps=[s.strip() for s in steps if s.strip()],
                allergens=list(dict.fromkeys(allergens)),
                photo_label=photo_label,
            )
        )

    async def get_recipe_detail(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> RecipeDetail:
        await self._require_variant(tenant_id, product_variant_id)
        detail = await self._repo.get_recipe_detail(tenant_id, product_variant_id)
        if detail is None:
            raise NotFoundError(
                f"La variante no tiene detalles de receta: {product_variant_id}"
            )
        return detail

    # --- Recipe card (aggregated read for kitchen screens) ------------------
    async def get_recipe_card(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> RecipeCard:
        await self._require_variant(tenant_id, product_variant_id)
        ingredients = await self._repo.list_bom_resolved(
            tenant_id, product_variant_id
        )
        detail = await self._repo.get_recipe_detail(tenant_id, product_variant_id)
        if not ingredients and detail is None:
            raise NotFoundError(
                f"La variante no tiene receta: {product_variant_id}"
            )
        return RecipeCard(
            product_variant_id=product_variant_id,
            ingredients=ingredients,
            steps=detail.steps if detail else [],
            allergens=detail.allergens if detail else [],
            photo_label=detail.photo_label if detail else None,
        )
