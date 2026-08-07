"""Los tres hechos que hacen falta para decidir si un cliente puede tocar su pedido.

Sólo `SELECT`. Misma postura que los lectores de alertas: leer directo los modelos del módulo
observado en vez de arrastrar aquí tres servicios enteros con sus escrituras. Lo que este
fichero devuelve son datos planos —una lista de estados, una cadena, un número—, así que el
servicio de edición se prueba con un doble de tres métodos y sin base de datos.

Los tres, y por qué cada uno:

- **Estados de las estaciones de un ítem** → la ventana por ítem. La granularidad real es
  (ítem × estación), no el pedido.
- **Estado de la entrega** → la ventana por pedido. `None` cuando el pedido no se reparte, que
  es lo que distingue "hasta que arranca la moto" de "hasta que está listo en el mostrador".
- **Lo pagado** → la regla de las líneas congeladas. Pagar no cierra la comanda, así que hay
  que preguntarlo aparte del estado.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.delivery.infrastructure.models import OrderDeliveryModel
from restaurante.modules.kitchen.infrastructure.models import OrderItemStationModel
from restaurante.modules.orders.domain.entities import CLAIM_PENDING
from restaurante.modules.orders.infrastructure.models import (
    OrderPaymentClaimModel,
    OrderPaymentModel,
)


class SqlAlchemyOrderEditReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def station_statuses(
        self, tenant_id: uuid.UUID, order_item_id: uuid.UUID
    ) -> list[str]:
        """Los estados de cocina de ESE ítem. Vacío = todavía no lo envió nadie."""
        stmt = select(OrderItemStationModel.status).where(
            OrderItemStationModel.tenant_id == tenant_id,
            OrderItemStationModel.order_item_id == order_item_id,
        )
        return list((await self._session.execute(stmt)).scalars())

    async def delivery_status(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> str | None:
        """El estado de su entrega, o `None` si este pedido no se reparte."""
        stmt = select(OrderDeliveryModel.delivery_status).where(
            OrderDeliveryModel.tenant_id == tenant_id,
            OrderDeliveryModel.order_id == order_id,
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def paid_total(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> Decimal:
        """Lo recibido por este pedido. Un abono cuenta; lo que congela es cubrir el total."""
        stmt = select(func.coalesce(func.sum(OrderPaymentModel.amount), 0)).where(
            OrderPaymentModel.tenant_id == tenant_id,
            OrderPaymentModel.order_id == order_id,
        )
        return Decimal(str((await self._session.execute(stmt)).scalar_one() or 0))

    async def pending_payment_proof(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> bool:
        """¿Mandó un comprobante que nadie ha mirado?

        Es una tabla distinta de la de pagos a propósito: lo que hay aquí NO suma al saldo.
        """
        stmt = select(OrderPaymentClaimModel.id).where(
            OrderPaymentClaimModel.tenant_id == tenant_id,
            OrderPaymentClaimModel.order_id == order_id,
            OrderPaymentClaimModel.status == CLAIM_PENDING,
        )
        return (await self._session.execute(stmt)).scalars().first() is not None
