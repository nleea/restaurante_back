"""Persistence adapter for the Recipes / BOM module over SQLAlchemy async.

Each write method commits its own unit of work and filters explicitly by
``tenant_id`` as defense in depth on top of the automatic tenancy filter.
Uniqueness violations on a recipe line are translated to ``ConflictError``.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.catalog.infrastructure.models import UnitOfMeasureModel
from restaurante.modules.menu.infrastructure.models import ProductVariantModel
from restaurante.modules.recipes.domain.entities import (
    Ingredient,
    RecipeCardIngredient,
    RecipeDetail,
    RecipeItem,
)
from restaurante.modules.recipes.infrastructure.models import (
    IngredientModel,
    RecipeDetailModel,
    RecipeItemModel,
)
from restaurante.shared.domain.errors import ConflictError


def _ingredient(m: IngredientModel) -> Ingredient:
    return Ingredient(
        id=m.id,
        tenant_id=m.tenant_id,
        name=m.name,
        unit_of_measure_id=m.unit_of_measure_id,
        is_active=m.is_active,
    )


def _recipe_item(m: RecipeItemModel) -> RecipeItem:
    return RecipeItem(
        id=m.id,
        tenant_id=m.tenant_id,
        product_variant_id=m.product_variant_id,
        ingredient_id=m.ingredient_id,
        quantity=m.quantity,
        unit_of_measure_id=m.unit_of_measure_id,
    )


def _recipe_detail(m: RecipeDetailModel) -> RecipeDetail:
    return RecipeDetail(
        id=m.id,
        tenant_id=m.tenant_id,
        product_variant_id=m.product_variant_id,
        steps=list(m.steps or []),
        allergens=list(m.allergens or []),
        photo_label=m.photo_label,
    )


class SqlAlchemyRecipesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reference existence checks ----------------------------------------
    async def unit_exists(self, unit_of_measure_id: uuid.UUID) -> bool:
        stmt = select(UnitOfMeasureModel.id).where(
            UnitOfMeasureModel.id == unit_of_measure_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def variant_exists(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> bool:
        stmt = select(ProductVariantModel.id).where(
            ProductVariantModel.id == product_variant_id,
            ProductVariantModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Ingredients -------------------------------------------------------
    async def create_ingredient(self, ingredient: Ingredient) -> Ingredient:
        model = IngredientModel(
            tenant_id=ingredient.tenant_id,
            name=ingredient.name,
            unit_of_measure_id=ingredient.unit_of_measure_id,
            is_active=ingredient.is_active,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _ingredient(model)

    async def _get_ingredient_model(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> IngredientModel | None:
        stmt = select(IngredientModel).where(
            IngredientModel.id == ingredient_id,
            IngredientModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_ingredient(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> Ingredient | None:
        model = await self._get_ingredient_model(tenant_id, ingredient_id)
        return _ingredient(model) if model else None

    async def list_ingredients(
        self, tenant_id: uuid.UUID, *, active: bool | None = None
    ) -> list[Ingredient]:
        stmt = select(IngredientModel).where(IngredientModel.tenant_id == tenant_id)
        if active is not None:
            stmt = stmt.where(IngredientModel.is_active.is_(active))
        stmt = stmt.order_by(IngredientModel.name)
        return [_ingredient(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_ingredient(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID, fields: dict[str, Any]
    ) -> Ingredient | None:
        model = await self._get_ingredient_model(tenant_id, ingredient_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _ingredient(model)

    # --- Recipe items (BOM) ------------------------------------------------
    async def create_recipe_item(self, item: RecipeItem) -> RecipeItem:
        model = RecipeItemModel(
            tenant_id=item.tenant_id,
            product_variant_id=item.product_variant_id,
            ingredient_id=item.ingredient_id,
            quantity=item.quantity,
            unit_of_measure_id=item.unit_of_measure_id,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(
                "Ese insumo ya forma parte de la receta de la variante."
            ) from exc
        await self._session.refresh(model)
        return _recipe_item(model)

    async def _get_recipe_item_model(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> RecipeItemModel | None:
        stmt = select(RecipeItemModel).where(
            RecipeItemModel.id == item_id,
            RecipeItemModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_recipe_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> RecipeItem | None:
        model = await self._get_recipe_item_model(tenant_id, item_id)
        return _recipe_item(model) if model else None

    async def recipe_item_exists(
        self,
        tenant_id: uuid.UUID,
        product_variant_id: uuid.UUID,
        ingredient_id: uuid.UUID,
    ) -> bool:
        stmt = select(RecipeItemModel.id).where(
            RecipeItemModel.tenant_id == tenant_id,
            RecipeItemModel.product_variant_id == product_variant_id,
            RecipeItemModel.ingredient_id == ingredient_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def list_recipe_items(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> list[RecipeItem]:
        stmt = (
            select(RecipeItemModel)
            .where(
                RecipeItemModel.tenant_id == tenant_id,
                RecipeItemModel.product_variant_id == product_variant_id,
            )
            .order_by(RecipeItemModel.id)
        )
        return [_recipe_item(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_recipe_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> RecipeItem | None:
        model = await self._get_recipe_item_model(tenant_id, item_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _recipe_item(model)

    async def delete_recipe_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            sql_delete(RecipeItemModel).where(
                RecipeItemModel.tenant_id == tenant_id,
                RecipeItemModel.id == item_id,
            )
        )
        await self._session.commit()

    # --- Recipe details (steps + allergens) ----------------------------------
    async def _get_detail_model(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> RecipeDetailModel | None:
        stmt = select(RecipeDetailModel).where(
            RecipeDetailModel.tenant_id == tenant_id,
            RecipeDetailModel.product_variant_id == product_variant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def upsert_recipe_detail(self, detail: RecipeDetail) -> RecipeDetail:
        model = await self._get_detail_model(
            detail.tenant_id, detail.product_variant_id
        )
        if model is None:
            model = RecipeDetailModel(
                tenant_id=detail.tenant_id,
                product_variant_id=detail.product_variant_id,
            )
            self._session.add(model)
        model.steps = detail.steps
        model.allergens = detail.allergens
        model.photo_label = detail.photo_label
        await self._session.commit()
        await self._session.refresh(model)
        return _recipe_detail(model)

    async def get_recipe_detail(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> RecipeDetail | None:
        model = await self._get_detail_model(tenant_id, product_variant_id)
        return _recipe_detail(model) if model else None

    # --- Recipe card (aggregated read for kitchen screens) -------------------
    async def list_bom_resolved(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> list[RecipeCardIngredient]:
        stmt = (
            select(
                IngredientModel.name,
                RecipeItemModel.quantity,
                UnitOfMeasureModel.abbreviation,
            )
            .join(
                IngredientModel,
                IngredientModel.id == RecipeItemModel.ingredient_id,
            )
            .join(
                UnitOfMeasureModel,
                UnitOfMeasureModel.id == RecipeItemModel.unit_of_measure_id,
            )
            .where(
                RecipeItemModel.tenant_id == tenant_id,
                RecipeItemModel.product_variant_id == product_variant_id,
            )
            .order_by(IngredientModel.name)
        )
        return [
            RecipeCardIngredient(name=row[0], quantity=row[1], unit=row[2])
            for row in (await self._session.execute(stmt)).all()
        ]
