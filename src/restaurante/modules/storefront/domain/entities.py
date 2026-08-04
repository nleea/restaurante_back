"""Framework-free read-model of the public storefront.

Plain dataclasses describing the customer-safe menu (categories + products with
their primary-branch price, sellable variant, available addons and the recipe-derived
removable ingredients). Deliberately NO cost, BOM quantities or other internal fields —
these are the only shapes the public surface may expose.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class StoreBranch:
    """A branch as the customer sees it when choosing where to order from.

    ``code`` is the human-readable identifier that addresses the branch in the public
    URL (`/store/<code>`); see `branches.code`, unique per tenant.
    """

    id: uuid.UUID
    code: str
    name: str
    address: str | None
    #: Teléfono público de la sede: es el WhatsApp al que el cliente manda su comprobante.
    phone: str | None = None


@dataclass
class StoreCategory:
    id: uuid.UUID
    name: str


@dataclass
class StoreAddon:
    id: uuid.UUID
    name: str
    price: Decimal


@dataclass
class StoreProduct:
    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    description: str | None
    image_url: str | None
    # Primary-branch active price; ``None`` when the product has no active price there.
    price: Decimal | None
    # One sellable (active) product variant id; ``None`` when the product has none.
    variant_id: uuid.UUID | None
    addons: list[StoreAddon] = field(default_factory=list)
    removable_ingredients: list[str] = field(default_factory=list)


@dataclass
class StoreMenu:
    categories: list[StoreCategory] = field(default_factory=list)
    products: list[StoreProduct] = field(default_factory=list)


@dataclass
class StoreVariant:
    """Cómo se llama y qué se le puede quitar a lo que YA está en un pedido.

    Se describe por variante y no por producto porque es la variante lo que la línea guarda.
    A diferencia de la carta, esto NO filtra por variante activa: un pedido puede tener algo
    que el negocio acaba de retirar del menú, y el cliente tiene derecho a ver su nombre en
    vez de un hueco.
    """

    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    removable_ingredients: list[str] = field(default_factory=list)
