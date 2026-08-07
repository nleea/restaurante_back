"""Pydantic schemas for the Menu API."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

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


# --- Appearance (public carta config) ---------------------------------------
# The backend's copy of the shared contract, kept in lockstep with
# `front/src/lib/menuAppearance.ts::MenuAppearanceConfig`. The persisted JSONB is
# camelCase (the storefront reads the same object), so every model serializes with
# camelCase aliases while accepting either casing on input. Unknown keys are ignored
# (forward-compatibility); missing/mistyped core fields raise 422.


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


class ThemeSchema(_CamelModel):
    primary_color: str
    secondary_color: str
    background_color: str
    text_color: str
    accent_color: str
    font_family: str


class BrandSchema(_CamelModel):
    logo_url: str
    banner_url: str
    restaurant_name: str


class GridPositionSchema(_CamelModel):
    x: int
    y: int


class BlockSchema(_CamelModel):
    id: str
    visible: bool
    position: GridPositionSchema
    size: str


class DishCardShowSchema(_CamelModel):
    image: bool
    description: bool
    price: bool
    addon_hint: bool
    removable_hint: bool


class DishCardSchema(_CamelModel):
    style: str
    show: DishCardShowSchema


class DishDetailSectionSchema(_CamelModel):
    id: str
    visible: bool


class DishDetailSchema(_CamelModel):
    sections: list[DishDetailSectionSchema]


class PromoContentSchema(_CamelModel):
    title: str
    body: str
    image_url: str


class HoursRowSchema(_CamelModel):
    label: str
    value: str


class HoursContentSchema(_CamelModel):
    rows: list[HoursRowSchema]


class TestimonialSchema(_CamelModel):
    author: str
    quote: str


class TestimonialsContentSchema(_CamelModel):
    items: list[TestimonialSchema]


class GalleryContentSchema(_CamelModel):
    image_urls: list[str]


class BlockContentSchema(_CamelModel):
    promo: PromoContentSchema
    hours: HoursContentSchema
    testimonials: TestimonialsContentSchema
    gallery: GalleryContentSchema


class MenuAppearanceConfigSchema(BaseModel):
    """Full public-carta appearance document (theme/brand/blocks/dishCard/…).

    Top-level field names deliberately match the wire contract (camelCase for the
    multi-word ones) so this model can be used directly as a FastAPI request/response
    body without per-field aliases — the nested models carry the camelCase aliasing.
    """

    model_config = ConfigDict(extra="ignore")

    theme: ThemeSchema
    brand: BrandSchema
    blocks: list[BlockSchema]
    dishCard: DishCardSchema  # noqa: N815 — mirrors the frontend contract key
    dishDetail: DishDetailSchema  # noqa: N815 — mirrors the frontend contract key
    blockContent: BlockContentSchema  # noqa: N815 — mirrors the frontend contract key
