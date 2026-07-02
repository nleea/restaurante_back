"""ORM models of the Menu module.

Tenant-scoped sellable catalog. `categories`, `products`, variants and `addons`
are tenant-level entities (`TenantScopedMixin`); only `product_prices` is
branch-scoped (`BranchScopedMixin`), since each branch may sell the same product
at a different price.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import (
    Base,
    BranchScopedMixin,
    TenantScopedMixin,
    TimestampMixin,
)


class CategoryModel(Base, TenantScopedMixin):
    """Hierarchical product category (optional self-reference to a parent)."""

    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    parent_category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ProductModel(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ProductPriceModel(Base, BranchScopedMixin):
    """Per-branch selling price of a product."""

    __tablename__ = "product_prices"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "branch_id", name="uq_product_prices_product_branch"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class VariantGroupModel(Base, TenantScopedMixin):
    """Group of mutually-related variant options for a product (e.g. size)."""

    __tablename__ = "variant_groups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    single_selection: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class VariantOptionModel(Base, TenantScopedMixin):
    """A single selectable option inside a variant group (e.g. large)."""

    __tablename__ = "variant_options"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    variant_group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("variant_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    extra_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AddonModel(Base, TenantScopedMixin):
    """Optional extra that can be attached to products (e.g. extra cheese)."""

    __tablename__ = "addons"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ProductAddonModel(Base, TenantScopedMixin):
    """Bridge: which addons are available for a product."""

    __tablename__ = "product_addons"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "addon_id", name="uq_product_addons_product_addon"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    addon_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("addons.id", ondelete="CASCADE"), nullable=False, index=True
    )


class ProductVariantModel(Base, TenantScopedMixin):
    """A concrete sellable variant (SKU) of a product."""

    __tablename__ = "product_variants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ProductVariantOptionModel(Base, TenantScopedMixin):
    """Bridge: which variant options make up a concrete product variant."""

    __tablename__ = "product_variant_options"
    __table_args__ = (
        UniqueConstraint(
            "product_variant_id",
            "variant_option_id",
            name="uq_product_variant_options_variant_option",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_variant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    variant_option_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("variant_options.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
