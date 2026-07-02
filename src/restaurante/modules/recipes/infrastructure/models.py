"""ORM models of the Recipes / BOM module.

Recipes are the only link between "what I sell" (catalog product variants) and
"what I have in stock" (inventory ingredients). Both entities are tenant-scoped
(`TenantScopedMixin`), so the automatic tenant filter applies.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import JSON, Boolean, ForeignKey, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import Base, TenantScopedMixin


class IngredientModel(Base, TenantScopedMixin):
    __tablename__ = "ingredients"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    unit_of_measure_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RecipeItemModel(Base, TenantScopedMixin):
    __tablename__ = "recipe_items"
    __table_args__ = (
        UniqueConstraint(
            "product_variant_id",
            "ingredient_id",
            name="uq_recipe_items_variant_ingredient",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_variant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ingredients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit_of_measure_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )


class RecipeDetailModel(Base, TenantScopedMixin):
    """Cook-facing recipe extras (preparation steps, allergens) per product variant.

    `steps` and `allergens` are JSON string arrays: steps are an ordered text list, and the
    allergen vocabulary is closed at the schema layer (see `domain.entities.ALLERGEN_KEYS`),
    so neither warrants its own table.
    """

    __tablename__ = "recipe_details"
    __table_args__ = (
        UniqueConstraint(
            "product_variant_id",
            name="uq_recipe_details_variant",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_variant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    steps: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allergens: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    photo_label: Mapped[str | None] = mapped_column(String(150), nullable=True)
