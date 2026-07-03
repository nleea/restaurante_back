"""Pydantic schemas for the Recipes API."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

AllergenKey = Literal["gluten", "dairy", "nuts", "shellfish", "vegan"]

# --- Responses --------------------------------------------------------------


class IngredientResponse(BaseModel):
    id: uuid.UUID
    name: str
    category: str | None = None
    unit_of_measure_id: uuid.UUID
    is_active: bool


class RecipeItemResponse(BaseModel):
    id: uuid.UUID
    product_variant_id: uuid.UUID
    ingredient_id: uuid.UUID
    quantity: Decimal
    unit_of_measure_id: uuid.UUID


# --- Requests ---------------------------------------------------------------


class CreateIngredientRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    category: str | None = Field(default=None, max_length=50)
    unit_of_measure_id: uuid.UUID

    @field_validator("category")
    @classmethod
    def _trim_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class UpdateIngredientRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    category: str | None = Field(default=None, max_length=50)
    unit_of_measure_id: uuid.UUID | None = None
    is_active: bool | None = None

    @field_validator("category")
    @classmethod
    def _trim_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class AddRecipeItemRequest(BaseModel):
    ingredient_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    unit_of_measure_id: uuid.UUID


class UpdateRecipeItemRequest(BaseModel):
    quantity: Decimal | None = Field(default=None, gt=0)
    unit_of_measure_id: uuid.UUID | None = None


# --- Recipe details + card ----------------------------------------------------


class RecipeDetailResponse(BaseModel):
    id: uuid.UUID
    product_variant_id: uuid.UUID
    steps: list[str]
    allergens: list[AllergenKey]
    photo_label: str | None


class UpsertRecipeDetailRequest(BaseModel):
    steps: list[str] = Field(default_factory=list, max_length=50)
    allergens: list[AllergenKey] = Field(default_factory=list, max_length=10)
    photo_label: str | None = Field(default=None, max_length=150)


class RecipeCardIngredientResponse(BaseModel):
    name: str
    quantity: Decimal
    unit: str


class RecipeCardResponse(BaseModel):
    product_variant_id: uuid.UUID
    ingredients: list[RecipeCardIngredientResponse]
    steps: list[str]
    allergens: list[AllergenKey]
    photo_label: str | None
