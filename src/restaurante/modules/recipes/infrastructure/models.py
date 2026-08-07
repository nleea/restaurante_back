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
    # Free-text grouping for the inventory board's filter ("Carnes", "Lácteos", …).
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    unit_of_measure_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # A diner may remove this insumo from a dish in the public carta (global per
    # insumo, not per recipe line). Filters the "quitar" list; defaults to true.
    is_customer_removable: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    # Which kitchen station works this insumo ("la carne se trabaja en la parrilla").
    # Feeds ONLY the station suggestion the kitchen derives from a product's recipe —
    # `route_order` never reads it, `product_stations` stays its single source of truth.
    #
    # Scope mismatch on purpose: ingredients are tenant-scoped and kitchen_stations are
    # branch-scoped, same as the pre-existing `product_stations`. The consumer absorbs it:
    # the suggestion filters to the active branch and reports an ingredient whose default
    # lives elsewhere as unassigned. Worst case in multi-branch is a thinner suggestion a
    # human overrides, never a mis-routed comanda.
    default_station_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("kitchen_stations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


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
    # Dónde se trabaja ESTE insumo en ESTE plato. Override del default del insumo, no reemplazo:
    # "¿dónde va el arroz?" no tiene respuesta global — se cocina en un plato y se fríe en otro —
    # y la línea de receta es justo el par (plato, insumo) donde sí la tiene.
    #
    # `SET NULL` al borrar la estación: caer al default del insumo es la degradación correcta;
    # bloquear o borrar una receta por reorganizar la cocina, no.
    station_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("kitchen_stations.id", ondelete="SET NULL"),
        nullable=True,
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
