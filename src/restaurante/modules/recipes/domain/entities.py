"""Framework-free domain entities of the Recipes / BOM module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Ingredient:
    tenant_id: uuid.UUID
    name: str
    unit_of_measure_id: uuid.UUID
    category: str | None = None
    is_active: bool = True
    # Whether a diner may remove this insumo from a dish in the public carta. Global
    # per insumo (not per recipe line); default true. Hides salt/oil-style noise.
    is_customer_removable: bool = True
    # Kitchen station where this insumo is worked. Optional: an insumo without one is
    # fully usable, it just contributes nothing to the station suggestion the kitchen
    # derives from a recipe. Never read by routing.
    default_station_id: uuid.UUID | None = None
    id: uuid.UUID | None = None


@dataclass
class RecipeItem:
    tenant_id: uuid.UUID
    product_variant_id: uuid.UUID
    ingredient_id: uuid.UUID
    quantity: Decimal
    unit_of_measure_id: uuid.UUID
    # Dónde se trabaja ESTE insumo en ESTE plato. Override del default del insumo: "¿dónde va el
    # arroz?" se cocina en un plato y se fríe en otro, y esta línea es el par (plato, insumo)
    # donde la pregunta sí tiene respuesta. Null = usar el default del insumo.
    station_id: uuid.UUID | None = None
    id: uuid.UUID | None = None


@dataclass
class IngredientCost:
    """An ingredient's current unit cost for live menu costing.

    ``unit_cost`` is the moving-average of the ingredient's purchase unit prices;
    it is ``None`` when the ingredient has no purchase history — unavailable, never
    zero, so the editor can distinguish "no cost yet" from "free".
    """

    ingredient_id: uuid.UUID
    unit_cost: Decimal | None = None


# Closed allergen vocabulary — mirrored by the API schema and the KDS frontend enum.
ALLERGEN_KEYS = ("gluten", "dairy", "nuts", "shellfish", "vegan")


@dataclass
class RecipeDetail:
    """Cook-facing recipe extras for one product variant (at most one row per variant)."""

    tenant_id: uuid.UUID
    product_variant_id: uuid.UUID
    steps: list[str]
    allergens: list[str]
    photo_label: str | None = None
    id: uuid.UUID | None = None


@dataclass
class RecipeCardIngredient:
    """A BOM line resolved for display: names instead of ids."""

    name: str
    quantity: Decimal
    unit: str


@dataclass
class RecipeCard:
    """Aggregated read model for kitchen screens: everything a cook needs in one shot."""

    product_variant_id: uuid.UUID
    ingredients: list[RecipeCardIngredient]
    steps: list[str]
    allergens: list[str]
    photo_label: str | None = None


@dataclass
class VariantMissingRecipe:
    """A sellable (active) variant that still has zero recipe items.

    Read model backing the "sin receta" list so legacy active-without-recipe
    variants are findable and fixable.
    """

    product_variant_id: uuid.UUID
    variant_name: str | None
    product_id: uuid.UUID
    product_name: str
