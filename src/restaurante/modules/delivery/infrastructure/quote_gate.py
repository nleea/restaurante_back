"""Adapter for `orders.DeliveryQuoteGate`: may this order's money be settled yet?

Lives in `delivery` and is wired into `orders` at the composition root, so the dependency runs
one way: orders knows an interface, delivery knows orders' data not at all.

The whole point is one ordering problem. A delivery order is created before its delivery fee
exists — that is the entire design of deferred quoting — so between intake and the quote landing
there is a window where `orders.total` is the food alone. Verifying a payment inside that window
charges the customer less than the restaurant is owed AND releases the order to the kitchen, and
by the time anyone notices, the food is out the door.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.delivery.infrastructure.models import OrderDeliveryModel

# Los dos estados en los que un domicilio SÍ puede cobrarse:
# - `quoted`: tiene tarifa congelada y el total del pedido ya la incluye.
# - `outside_coverage`: no hay domicilio que cobrar. El pedido no debería llegar aquí, pero si
#   el negocio decide cobrarlo igual (recogida acordada, entrega de favor), el total es correcto
#   tal cual está y bloquearlo sólo dejaría dinero sin registrar.
_SETTLEABLE = frozenset({"quoted", "outside_coverage"})

_PENDING = (
    "El domicilio de este pedido todavía no tiene valor calculado. "
    "Espera a que se cotice antes de verificar el pago."
)
_UNQUOTABLE = (
    "El domicilio de este pedido no se pudo cotizar ({reason}). "
    "Corrígelo antes de verificar el pago."
)


class SqlAlchemyDeliveryQuoteGate:
    """Implements `orders.DeliveryQuoteGate` by reading the order's delivery record."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def quote_blocker(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> str | None:
        row = (
            await self._session.execute(
                select(
                    OrderDeliveryModel.quote_status,
                    OrderDeliveryModel.quote_failure_reason,
                ).where(
                    OrderDeliveryModel.order_id == order_id,
                    OrderDeliveryModel.tenant_id == tenant_id,
                )
            )
        ).first()
        if row is None:
            # No es un domicilio. Mostrador y recogida nunca esperaron una cotización.
            return None
        status, reason = row
        if status in _SETTLEABLE:
            return None
        if status == "unquotable":
            return _UNQUOTABLE.format(reason=reason or "sin motivo registrado")
        return _PENDING
