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
    is_active: bool = True
    id: uuid.UUID | None = None


@dataclass
class RecipeItem:
    tenant_id: uuid.UUID
    product_variant_id: uuid.UUID
    ingredient_id: uuid.UUID
    quantity: Decimal
    unit_of_measure_id: uuid.UUID
    id: uuid.UUID | None = None


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
