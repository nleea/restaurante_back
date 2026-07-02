"""Pydantic schemas for the Menu API."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

# --- Responses --------------------------------------------------------------


class CategoryResponse(BaseModel):
    id: uuid.UUID
    name: str
    position: int
    is_active: bool
    parent_category_id: uuid.UUID | None = None


class ProductResponse(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    description: str | None = None
    image_url: str | None = None
    is_active: bool


class ProductPriceResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    branch_id: uuid.UUID
    price: Decimal
    is_active: bool


class VariantGroupResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    is_required: bool
    single_selection: bool


class VariantOptionResponse(BaseModel):
    id: uuid.UUID
    variant_group_id: uuid.UUID
    name: str
    extra_price: Decimal
    is_active: bool


class AddonResponse(BaseModel):
    id: uuid.UUID
    name: str
    price: Decimal
    is_active: bool


class ProductVariantResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    name: str | None = None
    is_active: bool
    # Derived: sum of the variant's composed options' extra_price (0 when plain).
    extra_price: Decimal


# --- Requests ---------------------------------------------------------------


class CreateCategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_category_id: uuid.UUID | None = None
    position: int = 0


class UpdateCategoryRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    parent_category_id: uuid.UUID | None = None
    position: int | None = None
    is_active: bool | None = None


class CreateProductRequest(BaseModel):
    category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    image_url: str | None = Field(default=None, max_length=500)


class UpdateProductRequest(BaseModel):
    category_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    image_url: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class SetPriceRequest(BaseModel):
    price: Decimal = Field(ge=0)
    is_active: bool = True


class CreateVariantGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    is_required: bool = True
    single_selection: bool = True


class UpdateVariantGroupRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_required: bool | None = None
    single_selection: bool | None = None


class CreateVariantOptionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    extra_price: Decimal = Field(default=Decimal(0), ge=0)
    is_active: bool = True


class UpdateVariantOptionRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    extra_price: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class CreateProductVariantRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    variant_option_ids: list[uuid.UUID] = Field(default_factory=list)


class UpdateProductVariantRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    is_active: bool | None = None


class CreateAddonRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(default=Decimal(0), ge=0)
    is_active: bool = True


class UpdateAddonRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    price: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None
