"""Application service for the Menu module.

Validates domain rules (referenced entities exist, branch belongs to the tenant)
and delegates persistence to `MenuRepository`. Accepts/returns framework-free
domain entities; the API layer maps to/from Pydantic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from restaurante.modules.menu.domain.entities import (
    Addon,
    Category,
    Product,
    ProductPrice,
    ProductVariant,
    VariantGroup,
    VariantOption,
)
from restaurante.modules.menu.domain.ports import MenuRepository
from restaurante.shared.domain.errors import NotFoundError, ValidationError


@dataclass(frozen=True)
class ProductVariantView:
    """A sellable variant plus its derived extra price (sum of composed options)."""

    id: uuid.UUID
    product_id: uuid.UUID
    name: str | None
    is_active: bool
    extra_price: Decimal


class MenuService:
    def __init__(self, repo: MenuRepository) -> None:
        self._repo = repo

    # --- internal guards ---------------------------------------------------
    async def _require_category(self, tenant_id: uuid.UUID, cid: uuid.UUID) -> Category:
        category = await self._repo.get_category(tenant_id, cid)
        if category is None:
            raise NotFoundError(f"Categoría no encontrada: {cid}")
        return category

    async def _require_product(self, tenant_id: uuid.UUID, pid: uuid.UUID) -> Product:
        product = await self._repo.get_product(tenant_id, pid)
        if product is None:
            raise NotFoundError(f"Producto no encontrado: {pid}")
        return product

    async def _require_group(
        self, tenant_id: uuid.UUID, gid: uuid.UUID
    ) -> VariantGroup:
        group = await self._repo.get_variant_group(tenant_id, gid)
        if group is None:
            raise NotFoundError(f"Grupo de variante no encontrado: {gid}")
        return group

    async def _require_addon(self, tenant_id: uuid.UUID, aid: uuid.UUID) -> Addon:
        addon = await self._repo.get_addon(tenant_id, aid)
        if addon is None:
            raise NotFoundError(f"Adición no encontrada: {aid}")
        return addon

    # --- Categories --------------------------------------------------------
    async def create_category(
        self,
        tenant_id: uuid.UUID,
        name: str,
        parent_category_id: uuid.UUID | None,
        position: int,
    ) -> Category:
        if parent_category_id is not None:
            await self._require_category(tenant_id, parent_category_id)
        return await self._repo.create_category(
            Category(
                tenant_id=tenant_id,
                name=name,
                position=position,
                parent_category_id=parent_category_id,
            )
        )

    async def list_categories(
        self,
        tenant_id: uuid.UUID,
        *,
        active: bool | None = None,
        parent_id: uuid.UUID | None = None,
    ) -> list[Category]:
        return await self._repo.list_categories(
            tenant_id, active=active, parent_id=parent_id
        )

    async def get_category(self, tenant_id: uuid.UUID, cid: uuid.UUID) -> Category:
        return await self._require_category(tenant_id, cid)

    async def update_category(
        self, tenant_id: uuid.UUID, cid: uuid.UUID, fields: dict[str, Any]
    ) -> Category:
        if fields.get("parent_category_id") is not None:
            await self._require_category(tenant_id, fields["parent_category_id"])
        updated = await self._repo.update_category(tenant_id, cid, fields)
        if updated is None:
            raise NotFoundError(f"Categoría no encontrada: {cid}")
        return updated

    async def delete_category(self, tenant_id: uuid.UUID, cid: uuid.UUID) -> None:
        await self._require_category(tenant_id, cid)
        await self._repo.delete_category(tenant_id, cid)

    # --- Products ----------------------------------------------------------
    async def create_product(
        self,
        tenant_id: uuid.UUID,
        category_id: uuid.UUID,
        name: str,
        description: str | None,
        image_url: str | None,
    ) -> Product:
        await self._require_category(tenant_id, category_id)
        return await self._repo.create_product(
            Product(
                tenant_id=tenant_id,
                category_id=category_id,
                name=name,
                description=description,
                image_url=image_url,
            )
        )

    async def list_products(
        self,
        tenant_id: uuid.UUID,
        *,
        category_id: uuid.UUID | None = None,
        active: bool | None = None,
    ) -> list[Product]:
        return await self._repo.list_products(
            tenant_id, category_id=category_id, active=active
        )

    async def get_product(self, tenant_id: uuid.UUID, pid: uuid.UUID) -> Product:
        return await self._require_product(tenant_id, pid)

    async def update_product(
        self, tenant_id: uuid.UUID, pid: uuid.UUID, fields: dict[str, Any]
    ) -> Product:
        if fields.get("category_id") is not None:
            await self._require_category(tenant_id, fields["category_id"])
        updated = await self._repo.update_product(tenant_id, pid, fields)
        if updated is None:
            raise NotFoundError(f"Producto no encontrado: {pid}")
        return updated

    async def delete_product(self, tenant_id: uuid.UUID, pid: uuid.UUID) -> None:
        await self._require_product(tenant_id, pid)
        await self._repo.delete_product(tenant_id, pid)

    # --- Prices ------------------------------------------------------------
    async def list_prices(
        self, tenant_id: uuid.UUID, pid: uuid.UUID
    ) -> list[ProductPrice]:
        await self._require_product(tenant_id, pid)
        return await self._repo.list_prices(tenant_id, pid)

    async def set_price(
        self,
        tenant_id: uuid.UUID,
        pid: uuid.UUID,
        branch_id: uuid.UUID,
        price: Decimal,
        is_active: bool,
    ) -> ProductPrice:
        await self._require_product(tenant_id, pid)
        if not await self._repo.branch_exists(tenant_id, branch_id):
            raise NotFoundError(f"Sucursal no encontrada: {branch_id}")
        return await self._repo.upsert_price(tenant_id, pid, branch_id, price, is_active)

    async def delete_price(
        self, tenant_id: uuid.UUID, pid: uuid.UUID, branch_id: uuid.UUID
    ) -> None:
        await self._repo.delete_price(tenant_id, pid, branch_id)

    # --- Variant groups / options -----------------------------------------
    async def create_variant_group(
        self,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
        name: str,
        is_required: bool,
        single_selection: bool,
    ) -> VariantGroup:
        await self._require_product(tenant_id, product_id)
        return await self._repo.create_variant_group(
            VariantGroup(
                tenant_id=tenant_id,
                product_id=product_id,
                name=name,
                is_required=is_required,
                single_selection=single_selection,
            )
        )

    async def list_variant_groups(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[VariantGroup]:
        await self._require_product(tenant_id, product_id)
        return await self._repo.list_variant_groups(tenant_id, product_id)

    async def update_variant_group(
        self, tenant_id: uuid.UUID, gid: uuid.UUID, fields: dict[str, Any]
    ) -> VariantGroup:
        updated = await self._repo.update_variant_group(tenant_id, gid, fields)
        if updated is None:
            raise NotFoundError(f"Grupo de variante no encontrado: {gid}")
        return updated

    async def delete_variant_group(self, tenant_id: uuid.UUID, gid: uuid.UUID) -> None:
        await self._require_group(tenant_id, gid)
        await self._repo.delete_variant_group(tenant_id, gid)

    async def create_variant_option(
        self,
        tenant_id: uuid.UUID,
        group_id: uuid.UUID,
        name: str,
        extra_price: Decimal,
        is_active: bool,
    ) -> VariantOption:
        await self._require_group(tenant_id, group_id)
        return await self._repo.create_variant_option(
            VariantOption(
                tenant_id=tenant_id,
                variant_group_id=group_id,
                name=name,
                extra_price=extra_price,
                is_active=is_active,
            )
        )

    async def list_variant_options(
        self, tenant_id: uuid.UUID, group_id: uuid.UUID
    ) -> list[VariantOption]:
        await self._require_group(tenant_id, group_id)
        return await self._repo.list_variant_options(tenant_id, group_id)

    async def update_variant_option(
        self, tenant_id: uuid.UUID, oid: uuid.UUID, fields: dict[str, Any]
    ) -> VariantOption:
        updated = await self._repo.update_variant_option(tenant_id, oid, fields)
        if updated is None:
            raise NotFoundError(f"Opción de variante no encontrada: {oid}")
        return updated

    async def delete_variant_option(self, tenant_id: uuid.UUID, oid: uuid.UUID) -> None:
        option = await self._repo.get_variant_option(tenant_id, oid)
        if option is None:
            raise NotFoundError(f"Opción de variante no encontrada: {oid}")
        await self._repo.delete_variant_option(tenant_id, oid)

    # --- Product variants (sellable SKUs) ----------------------------------
    async def _variant_view(
        self, tenant_id: uuid.UUID, variant: ProductVariant
    ) -> ProductVariantView:
        assert variant.id is not None  # persisted variant always has an id
        extra = await self._repo.extra_price_of(tenant_id, variant.id)
        return ProductVariantView(
            id=variant.id,
            product_id=variant.product_id,
            name=variant.name,
            is_active=variant.is_active,
            extra_price=extra,
        )

    async def create_product_variant(
        self,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
        name: str | None,
        option_ids: list[uuid.UUID],
    ) -> ProductVariantView:
        await self._require_product(tenant_id, product_id)
        if option_ids:
            valid = await self._repo.product_option_ids(tenant_id, product_id)
            foreign = [oid for oid in option_ids if oid not in valid]
            if foreign:
                raise ValidationError(
                    "Algunas opciones no pertenecen a este producto."
                )
        variant = await self._repo.create_product_variant(
            ProductVariant(tenant_id=tenant_id, product_id=product_id, name=name),
            option_ids,
        )
        return await self._variant_view(tenant_id, variant)

    async def list_product_variants(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[ProductVariantView]:
        await self._require_product(tenant_id, product_id)
        variants = await self._repo.list_product_variants(tenant_id, product_id)
        return [await self._variant_view(tenant_id, v) for v in variants]

    async def update_product_variant(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID, fields: dict[str, Any]
    ) -> ProductVariantView:
        updated = await self._repo.update_product_variant(tenant_id, variant_id, fields)
        if updated is None:
            raise NotFoundError(f"Variante no encontrada: {variant_id}")
        return await self._variant_view(tenant_id, updated)

    async def delete_product_variant(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> None:
        variant = await self._repo.get_product_variant(tenant_id, variant_id)
        if variant is None:
            raise NotFoundError(f"Variante no encontrada: {variant_id}")
        await self._repo.delete_product_variant(tenant_id, variant_id)

    # --- Addons & product<->addon -----------------------------------------
    async def create_addon(
        self, tenant_id: uuid.UUID, name: str, price: Decimal, is_active: bool
    ) -> Addon:
        return await self._repo.create_addon(
            Addon(tenant_id=tenant_id, name=name, price=price, is_active=is_active)
        )

    async def list_addons(
        self, tenant_id: uuid.UUID, *, active: bool | None = None
    ) -> list[Addon]:
        return await self._repo.list_addons(tenant_id, active=active)

    async def update_addon(
        self, tenant_id: uuid.UUID, aid: uuid.UUID, fields: dict[str, Any]
    ) -> Addon:
        updated = await self._repo.update_addon(tenant_id, aid, fields)
        if updated is None:
            raise NotFoundError(f"Adición no encontrada: {aid}")
        return updated

    async def delete_addon(self, tenant_id: uuid.UUID, aid: uuid.UUID) -> None:
        await self._require_addon(tenant_id, aid)
        await self._repo.delete_addon(tenant_id, aid)

    async def list_product_addons(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[Addon]:
        await self._require_product(tenant_id, product_id)
        return await self._repo.list_product_addons(tenant_id, product_id)

    async def attach_addon(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, addon_id: uuid.UUID
    ) -> None:
        await self._require_product(tenant_id, product_id)
        await self._require_addon(tenant_id, addon_id)
        await self._repo.attach_addon(tenant_id, product_id, addon_id)

    async def detach_addon(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, addon_id: uuid.UUID
    ) -> None:
        await self._repo.detach_addon(tenant_id, product_id, addon_id)
