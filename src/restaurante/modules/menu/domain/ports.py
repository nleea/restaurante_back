"""Ports (interfaces) of the Menu module."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Protocol

from restaurante.modules.menu.domain.entities import (
    Addon,
    Category,
    Product,
    ProductPrice,
    ProductVariant,
    VariantGroup,
    VariantOption,
)


class MenuRepository(Protocol):
    # --- Categories --------------------------------------------------------
    async def create_category(self, category: Category) -> Category: ...

    async def get_category(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID
    ) -> Category | None: ...

    async def list_categories(
        self,
        tenant_id: uuid.UUID,
        *,
        active: bool | None = None,
        parent_id: uuid.UUID | None = None,
    ) -> list[Category]: ...

    async def update_category(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID, fields: dict[str, Any]
    ) -> Category | None: ...

    async def delete_category(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID
    ) -> None: ...

    # --- Products ----------------------------------------------------------
    async def create_product(self, product: Product) -> Product: ...

    async def get_product(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> Product | None: ...

    async def list_products(
        self,
        tenant_id: uuid.UUID,
        *,
        category_id: uuid.UUID | None = None,
        active: bool | None = None,
    ) -> list[Product]: ...

    async def update_product(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, fields: dict[str, Any]
    ) -> Product | None: ...

    async def delete_product(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> None: ...

    # --- Prices (per branch) ----------------------------------------------
    async def branch_exists(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool: ...

    async def upsert_price(
        self,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
        branch_id: uuid.UUID,
        price: Decimal,
        is_active: bool,
    ) -> ProductPrice: ...

    async def list_prices(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[ProductPrice]: ...

    async def delete_price(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, branch_id: uuid.UUID
    ) -> None: ...

    # --- Variant groups / options -----------------------------------------
    async def create_variant_group(self, group: VariantGroup) -> VariantGroup: ...

    async def get_variant_group(
        self, tenant_id: uuid.UUID, group_id: uuid.UUID
    ) -> VariantGroup | None: ...

    async def list_variant_groups(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[VariantGroup]: ...

    async def update_variant_group(
        self, tenant_id: uuid.UUID, group_id: uuid.UUID, fields: dict[str, Any]
    ) -> VariantGroup | None: ...

    async def delete_variant_group(
        self, tenant_id: uuid.UUID, group_id: uuid.UUID
    ) -> None: ...

    async def create_variant_option(
        self, option: VariantOption
    ) -> VariantOption: ...

    async def get_variant_option(
        self, tenant_id: uuid.UUID, option_id: uuid.UUID
    ) -> VariantOption | None: ...

    async def list_variant_options(
        self, tenant_id: uuid.UUID, group_id: uuid.UUID
    ) -> list[VariantOption]: ...

    async def update_variant_option(
        self, tenant_id: uuid.UUID, option_id: uuid.UUID, fields: dict[str, Any]
    ) -> VariantOption | None: ...

    async def delete_variant_option(
        self, tenant_id: uuid.UUID, option_id: uuid.UUID
    ) -> None: ...

    # --- Product variants (sellable SKUs) ----------------------------------
    async def create_product_variant(
        self, variant: ProductVariant, option_ids: list[uuid.UUID]
    ) -> ProductVariant: ...

    async def get_product_variant(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> ProductVariant | None: ...

    async def list_product_variants(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[ProductVariant]: ...

    async def update_product_variant(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID, fields: dict[str, Any]
    ) -> ProductVariant | None: ...

    async def delete_product_variant(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> None: ...

    async def extra_price_of(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> Decimal: ...

    async def product_option_ids(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> set[uuid.UUID]: ...

    # --- Addons & product<->addon -----------------------------------------
    async def create_addon(self, addon: Addon) -> Addon: ...

    async def get_addon(
        self, tenant_id: uuid.UUID, addon_id: uuid.UUID
    ) -> Addon | None: ...

    async def list_addons(
        self, tenant_id: uuid.UUID, *, active: bool | None = None
    ) -> list[Addon]: ...

    async def update_addon(
        self, tenant_id: uuid.UUID, addon_id: uuid.UUID, fields: dict[str, Any]
    ) -> Addon | None: ...

    async def delete_addon(self, tenant_id: uuid.UUID, addon_id: uuid.UUID) -> None: ...

    async def list_product_addons(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[Addon]: ...

    async def attach_addon(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, addon_id: uuid.UUID
    ) -> None: ...

    async def detach_addon(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, addon_id: uuid.UUID
    ) -> None: ...
