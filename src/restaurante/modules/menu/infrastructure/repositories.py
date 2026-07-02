"""Persistence adapter for the Menu module over SQLAlchemy async.

Each write method commits its own unit of work (admin actions are atomic) and
filters explicitly by ``tenant_id`` as defense in depth on top of the automatic
tenancy filter. FK violations on delete (RESTRICT) are translated to
``ConflictError``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.menu.domain.entities import (
    Addon,
    Category,
    Product,
    ProductPrice,
    ProductVariant,
    VariantGroup,
    VariantOption,
)
from restaurante.modules.menu.infrastructure.models import (
    AddonModel,
    CategoryModel,
    ProductAddonModel,
    ProductModel,
    ProductPriceModel,
    ProductVariantModel,
    ProductVariantOptionModel,
    VariantGroupModel,
    VariantOptionModel,
)
from restaurante.shared.domain.errors import ConflictError
from restaurante.shared.tenancy.models import BranchModel


def _category(m: CategoryModel) -> Category:
    return Category(
        id=m.id,
        tenant_id=m.tenant_id,
        name=m.name,
        position=m.position,
        is_active=m.is_active,
        parent_category_id=m.parent_category_id,
    )


def _product(m: ProductModel) -> Product:
    return Product(
        id=m.id,
        tenant_id=m.tenant_id,
        category_id=m.category_id,
        name=m.name,
        is_active=m.is_active,
        description=m.description,
        image_url=m.image_url,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _price(m: ProductPriceModel) -> ProductPrice:
    return ProductPrice(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        product_id=m.product_id,
        price=m.price,
        is_active=m.is_active,
    )


def _group(m: VariantGroupModel) -> VariantGroup:
    return VariantGroup(
        id=m.id,
        tenant_id=m.tenant_id,
        product_id=m.product_id,
        name=m.name,
        is_required=m.is_required,
        single_selection=m.single_selection,
    )


def _option(m: VariantOptionModel) -> VariantOption:
    return VariantOption(
        id=m.id,
        tenant_id=m.tenant_id,
        variant_group_id=m.variant_group_id,
        name=m.name,
        extra_price=m.extra_price,
        is_active=m.is_active,
    )


def _addon(m: AddonModel) -> Addon:
    return Addon(
        id=m.id,
        tenant_id=m.tenant_id,
        name=m.name,
        price=m.price,
        is_active=m.is_active,
    )


def _variant(m: ProductVariantModel) -> ProductVariant:
    return ProductVariant(
        id=m.id,
        tenant_id=m.tenant_id,
        product_id=m.product_id,
        name=m.name,
        is_active=m.is_active,
    )


class SqlAlchemyMenuRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _delete_or_conflict(self, model: object) -> None:
        await self._session.delete(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(
                "No se puede eliminar: tiene elementos dependientes."
            ) from exc

    # --- Categories --------------------------------------------------------
    async def create_category(self, category: Category) -> Category:
        model = CategoryModel(
            tenant_id=category.tenant_id,
            name=category.name,
            position=category.position,
            is_active=category.is_active,
            parent_category_id=category.parent_category_id,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _category(model)

    async def get_category(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID
    ) -> Category | None:
        model = await self._get_category_model(tenant_id, category_id)
        return _category(model) if model else None

    async def _get_category_model(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID
    ) -> CategoryModel | None:
        stmt = select(CategoryModel).where(
            CategoryModel.id == category_id, CategoryModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_categories(
        self,
        tenant_id: uuid.UUID,
        *,
        active: bool | None = None,
        parent_id: uuid.UUID | None = None,
    ) -> list[Category]:
        stmt = select(CategoryModel).where(CategoryModel.tenant_id == tenant_id)
        if active is not None:
            stmt = stmt.where(CategoryModel.is_active.is_(active))
        if parent_id is not None:
            stmt = stmt.where(CategoryModel.parent_category_id == parent_id)
        stmt = stmt.order_by(CategoryModel.position, CategoryModel.name)
        return [_category(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_category(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID, fields: dict[str, Any]
    ) -> Category | None:
        model = await self._get_category_model(tenant_id, category_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _category(model)

    async def delete_category(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID
    ) -> None:
        model = await self._get_category_model(tenant_id, category_id)
        if model is not None:
            await self._delete_or_conflict(model)

    # --- Products ----------------------------------------------------------
    async def create_product(self, product: Product) -> Product:
        model = ProductModel(
            tenant_id=product.tenant_id,
            category_id=product.category_id,
            name=product.name,
            description=product.description,
            image_url=product.image_url,
            is_active=product.is_active,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _product(model)

    async def _get_product_model(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> ProductModel | None:
        stmt = select(ProductModel).where(
            ProductModel.id == product_id, ProductModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_product(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> Product | None:
        model = await self._get_product_model(tenant_id, product_id)
        return _product(model) if model else None

    async def list_products(
        self,
        tenant_id: uuid.UUID,
        *,
        category_id: uuid.UUID | None = None,
        active: bool | None = None,
    ) -> list[Product]:
        stmt = select(ProductModel).where(ProductModel.tenant_id == tenant_id)
        if category_id is not None:
            stmt = stmt.where(ProductModel.category_id == category_id)
        if active is not None:
            stmt = stmt.where(ProductModel.is_active.is_(active))
        stmt = stmt.order_by(ProductModel.name)
        return [_product(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_product(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, fields: dict[str, Any]
    ) -> Product | None:
        model = await self._get_product_model(tenant_id, product_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _product(model)

    async def delete_product(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> None:
        model = await self._get_product_model(tenant_id, product_id)
        if model is not None:
            await self._delete_or_conflict(model)

    # --- Prices ------------------------------------------------------------
    async def branch_exists(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool:
        stmt = select(BranchModel.id).where(
            BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def upsert_price(
        self,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
        branch_id: uuid.UUID,
        price: Decimal,
        is_active: bool,
    ) -> ProductPrice:
        stmt = select(ProductPriceModel).where(
            ProductPriceModel.tenant_id == tenant_id,
            ProductPriceModel.product_id == product_id,
            ProductPriceModel.branch_id == branch_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            model = ProductPriceModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                product_id=product_id,
                price=price,
                is_active=is_active,
            )
            self._session.add(model)
        else:
            model.price = price
            model.is_active = is_active
        await self._session.commit()
        await self._session.refresh(model)
        return _price(model)

    async def list_prices(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[ProductPrice]:
        stmt = select(ProductPriceModel).where(
            ProductPriceModel.tenant_id == tenant_id,
            ProductPriceModel.product_id == product_id,
        )
        return [_price(m) for m in (await self._session.execute(stmt)).scalars()]

    async def delete_price(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, branch_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            sql_delete(ProductPriceModel).where(
                ProductPriceModel.tenant_id == tenant_id,
                ProductPriceModel.product_id == product_id,
                ProductPriceModel.branch_id == branch_id,
            )
        )
        await self._session.commit()

    # --- Variant groups ----------------------------------------------------
    async def create_variant_group(self, group: VariantGroup) -> VariantGroup:
        model = VariantGroupModel(
            tenant_id=group.tenant_id,
            product_id=group.product_id,
            name=group.name,
            is_required=group.is_required,
            single_selection=group.single_selection,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _group(model)

    async def _get_group_model(
        self, tenant_id: uuid.UUID, group_id: uuid.UUID
    ) -> VariantGroupModel | None:
        stmt = select(VariantGroupModel).where(
            VariantGroupModel.id == group_id, VariantGroupModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_variant_group(
        self, tenant_id: uuid.UUID, group_id: uuid.UUID
    ) -> VariantGroup | None:
        model = await self._get_group_model(tenant_id, group_id)
        return _group(model) if model else None

    async def list_variant_groups(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[VariantGroup]:
        stmt = (
            select(VariantGroupModel)
            .where(
                VariantGroupModel.tenant_id == tenant_id,
                VariantGroupModel.product_id == product_id,
            )
            .order_by(VariantGroupModel.name)
        )
        return [_group(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_variant_group(
        self, tenant_id: uuid.UUID, group_id: uuid.UUID, fields: dict[str, Any]
    ) -> VariantGroup | None:
        model = await self._get_group_model(tenant_id, group_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _group(model)

    async def delete_variant_group(
        self, tenant_id: uuid.UUID, group_id: uuid.UUID
    ) -> None:
        model = await self._get_group_model(tenant_id, group_id)
        if model is not None:
            await self._delete_or_conflict(model)

    # --- Variant options ---------------------------------------------------
    async def create_variant_option(self, option: VariantOption) -> VariantOption:
        model = VariantOptionModel(
            tenant_id=option.tenant_id,
            variant_group_id=option.variant_group_id,
            name=option.name,
            extra_price=option.extra_price,
            is_active=option.is_active,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _option(model)

    async def _get_option_model(
        self, tenant_id: uuid.UUID, option_id: uuid.UUID
    ) -> VariantOptionModel | None:
        stmt = select(VariantOptionModel).where(
            VariantOptionModel.id == option_id,
            VariantOptionModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_variant_option(
        self, tenant_id: uuid.UUID, option_id: uuid.UUID
    ) -> VariantOption | None:
        model = await self._get_option_model(tenant_id, option_id)
        return _option(model) if model else None

    async def list_variant_options(
        self, tenant_id: uuid.UUID, group_id: uuid.UUID
    ) -> list[VariantOption]:
        stmt = (
            select(VariantOptionModel)
            .where(
                VariantOptionModel.tenant_id == tenant_id,
                VariantOptionModel.variant_group_id == group_id,
            )
            .order_by(VariantOptionModel.name)
        )
        return [_option(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_variant_option(
        self, tenant_id: uuid.UUID, option_id: uuid.UUID, fields: dict[str, Any]
    ) -> VariantOption | None:
        model = await self._get_option_model(tenant_id, option_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _option(model)

    async def delete_variant_option(
        self, tenant_id: uuid.UUID, option_id: uuid.UUID
    ) -> None:
        model = await self._get_option_model(tenant_id, option_id)
        if model is not None:
            await self._delete_or_conflict(model)

    # --- Product variants (sellable SKUs) ----------------------------------
    async def create_product_variant(
        self, variant: ProductVariant, option_ids: list[uuid.UUID]
    ) -> ProductVariant:
        model = ProductVariantModel(
            tenant_id=variant.tenant_id,
            product_id=variant.product_id,
            name=variant.name,
            is_active=variant.is_active,
        )
        self._session.add(model)
        await self._session.flush()
        for option_id in option_ids:
            self._session.add(
                ProductVariantOptionModel(
                    tenant_id=variant.tenant_id,
                    product_variant_id=model.id,
                    variant_option_id=option_id,
                )
            )
        await self._session.commit()
        await self._session.refresh(model)
        return _variant(model)

    async def _get_variant_model(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> ProductVariantModel | None:
        stmt = select(ProductVariantModel).where(
            ProductVariantModel.id == variant_id,
            ProductVariantModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_product_variant(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> ProductVariant | None:
        model = await self._get_variant_model(tenant_id, variant_id)
        return _variant(model) if model else None

    async def list_product_variants(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[ProductVariant]:
        stmt = (
            select(ProductVariantModel)
            .where(
                ProductVariantModel.tenant_id == tenant_id,
                ProductVariantModel.product_id == product_id,
            )
            .order_by(ProductVariantModel.name)
        )
        return [_variant(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_product_variant(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID, fields: dict[str, Any]
    ) -> ProductVariant | None:
        model = await self._get_variant_model(tenant_id, variant_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _variant(model)

    async def delete_product_variant(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> None:
        model = await self._get_variant_model(tenant_id, variant_id)
        if model is not None:
            await self._delete_or_conflict(model)

    async def extra_price_of(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> Decimal:
        stmt = (
            select(func.coalesce(func.sum(VariantOptionModel.extra_price), 0))
            .select_from(ProductVariantOptionModel)
            .join(
                VariantOptionModel,
                VariantOptionModel.id == ProductVariantOptionModel.variant_option_id,
            )
            .where(
                ProductVariantOptionModel.product_variant_id == variant_id,
                ProductVariantOptionModel.tenant_id == tenant_id,
            )
        )
        return Decimal((await self._session.execute(stmt)).scalar_one())

    async def product_option_ids(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> set[uuid.UUID]:
        stmt = (
            select(VariantOptionModel.id)
            .join(
                VariantGroupModel,
                VariantGroupModel.id == VariantOptionModel.variant_group_id,
            )
            .where(
                VariantGroupModel.tenant_id == tenant_id,
                VariantGroupModel.product_id == product_id,
            )
        )
        return set((await self._session.execute(stmt)).scalars())

    # --- Addons & product<->addon -----------------------------------------
    async def create_addon(self, addon: Addon) -> Addon:
        model = AddonModel(
            tenant_id=addon.tenant_id,
            name=addon.name,
            price=addon.price,
            is_active=addon.is_active,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _addon(model)

    async def _get_addon_model(
        self, tenant_id: uuid.UUID, addon_id: uuid.UUID
    ) -> AddonModel | None:
        stmt = select(AddonModel).where(
            AddonModel.id == addon_id, AddonModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_addon(
        self, tenant_id: uuid.UUID, addon_id: uuid.UUID
    ) -> Addon | None:
        model = await self._get_addon_model(tenant_id, addon_id)
        return _addon(model) if model else None

    async def list_addons(
        self, tenant_id: uuid.UUID, *, active: bool | None = None
    ) -> list[Addon]:
        stmt = select(AddonModel).where(AddonModel.tenant_id == tenant_id)
        if active is not None:
            stmt = stmt.where(AddonModel.is_active.is_(active))
        stmt = stmt.order_by(AddonModel.name)
        return [_addon(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_addon(
        self, tenant_id: uuid.UUID, addon_id: uuid.UUID, fields: dict[str, Any]
    ) -> Addon | None:
        model = await self._get_addon_model(tenant_id, addon_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _addon(model)

    async def delete_addon(self, tenant_id: uuid.UUID, addon_id: uuid.UUID) -> None:
        model = await self._get_addon_model(tenant_id, addon_id)
        if model is not None:
            await self._delete_or_conflict(model)

    async def list_product_addons(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[Addon]:
        stmt = (
            select(AddonModel)
            .join(ProductAddonModel, ProductAddonModel.addon_id == AddonModel.id)
            .where(
                ProductAddonModel.tenant_id == tenant_id,
                ProductAddonModel.product_id == product_id,
            )
            .order_by(AddonModel.name)
        )
        return [_addon(m) for m in (await self._session.execute(stmt)).scalars()]

    async def attach_addon(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, addon_id: uuid.UUID
    ) -> None:
        exists = (
            await self._session.execute(
                select(ProductAddonModel.id).where(
                    ProductAddonModel.tenant_id == tenant_id,
                    ProductAddonModel.product_id == product_id,
                    ProductAddonModel.addon_id == addon_id,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            self._session.add(
                ProductAddonModel(
                    tenant_id=tenant_id, product_id=product_id, addon_id=addon_id
                )
            )
            await self._session.commit()

    async def detach_addon(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, addon_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            sql_delete(ProductAddonModel).where(
                ProductAddonModel.tenant_id == tenant_id,
                ProductAddonModel.product_id == product_id,
                ProductAddonModel.addon_id == addon_id,
            )
        )
        await self._session.commit()
