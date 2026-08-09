"""Shared test helper: give a variant a price in a branch.

``OrderService.add_item`` no longer takes a price — it resolves one from
``product_prices`` for the order's branch plus the variant's composed surcharge — and it
**refuses the sale** when there is none, rather than selling at zero. So every happy-path
test that adds an item must have a priced product for its branch, exactly as it already
needs a recipe (the inventory safety net) and an open cash session.

That makes three safety nets at the sale boundary, and they fail the same way on purpose:
a variant with no recipe would not deduct stock, a product with no price would be given
away, and a branch with no open cash session has nobody accountable for the money. All
three refuse instead of degrading.

Seeded directly via ``SessionFactory`` (no HTTP, no RBAC), mirroring ``_cash.py``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from restaurante.modules.menu.infrastructure.models import (
    ProductPriceModel,
    ProductVariantModel,
)
from restaurante.shared.database import SessionFactory

#: El precio por defecto de las pruebas. Redondo a propósito: cuando un total no cuadra, aritmética
#: fácil es la diferencia entre ver el error y buscarlo.
DEFAULT_PRICE = Decimal("10000.00")


async def price_variant_for_branch(
    variant_id: uuid.UUID,
    branch_id: uuid.UUID,
    price: Decimal = DEFAULT_PRICE,
) -> Decimal:
    """Precia el PRODUCTO de esa variante en esa sede. Devuelve el precio puesto.

    Se recibe la variante y no el producto porque es lo que las pruebas tienen a mano —el
    identificador que le pasan a `add_item`—, y el salto variante → producto es justo el que hace
    `resolve_line_price`. Pedir el producto obligaría a cada prueba a saber que el precio es del
    producto y no de la variante, que es un detalle del modelo que no le aporta nada.
    """
    async with SessionFactory() as session:
        row = (
            await session.execute(
                select(ProductVariantModel.tenant_id, ProductVariantModel.product_id)
                .where(ProductVariantModel.id == variant_id)
                .execution_options(skip_tenant_filter=True)
            )
        ).one()
        tenant_id, product_id = row[0], row[1]
        session.add(
            ProductPriceModel(
                tenant_id=tenant_id,
                product_id=product_id,
                branch_id=branch_id,
                price=price,
                is_active=True,
            )
        )
        await session.commit()
    return price
