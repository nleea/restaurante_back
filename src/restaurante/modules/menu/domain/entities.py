"""Framework-free domain entities of the Menu module.

Plain dataclasses mirroring the ORM tables. They carry `tenant_id` (and
`branch_id` for branch-scoped entities) but know nothing about SQLAlchemy.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class Category:
    tenant_id: uuid.UUID
    name: str
    position: int = 0
    is_active: bool = True
    id: uuid.UUID | None = None
    parent_category_id: uuid.UUID | None = None


@dataclass
class Product:
    tenant_id: uuid.UUID
    category_id: uuid.UUID
    name: str
    is_active: bool = True
    id: uuid.UUID | None = None
    description: str | None = None
    image_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ProductPrice:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    product_id: uuid.UUID
    price: Decimal
    is_active: bool = True
    id: uuid.UUID | None = None


@dataclass
class VariantGroup:
    tenant_id: uuid.UUID
    product_id: uuid.UUID
    name: str
    is_required: bool = True
    single_selection: bool = True
    id: uuid.UUID | None = None


@dataclass
class VariantOption:
    tenant_id: uuid.UUID
    variant_group_id: uuid.UUID
    name: str
    extra_price: Decimal = Decimal(0)
    is_active: bool = True
    id: uuid.UUID | None = None


@dataclass
class Addon:
    tenant_id: uuid.UUID
    name: str
    price: Decimal = Decimal(0)
    is_active: bool = True
    id: uuid.UUID | None = None


@dataclass
class ProductAddon:
    tenant_id: uuid.UUID
    product_id: uuid.UUID
    addon_id: uuid.UUID
    id: uuid.UUID | None = None


@dataclass
class ProductVariant:
    tenant_id: uuid.UUID
    product_id: uuid.UUID
    is_active: bool = True
    id: uuid.UUID | None = None
    name: str | None = None


@dataclass
class ProductVariantOption:
    tenant_id: uuid.UUID
    product_variant_id: uuid.UUID
    variant_option_id: uuid.UUID
    id: uuid.UUID | None = None
