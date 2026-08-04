"""Dependency wiring for the Delivery API."""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.delivery.application.use_cases.manage_delivery import (
    DeliveryService,
)
from restaurante.modules.delivery.domain.ports import GeocodeQueue
from restaurante.modules.delivery.infrastructure.geocode_queue import ArqGeocodeQueue
from restaurante.modules.delivery.infrastructure.repositories import (
    SqlAlchemyDeliveryRepository,
)
from restaurante.modules.identity.infrastructure.api.deps import CurrentUserDep
from restaurante.modules.messaging.infrastructure.api.deps import (
    build_customer_channel,
)
from restaurante.modules.orders.application.use_cases.manage_orders import OrderService
from restaurante.modules.orders.application.use_cases.manage_payments import (
    PaymentService,
)
from restaurante.modules.orders.infrastructure.repositories import (
    SqlAlchemyOrdersRepository,
)
from restaurante.modules.staff.application.use_cases.manage_staff import StaffService
from restaurante.modules.staff.domain.entities import Employee
from restaurante.modules.staff.infrastructure.repositories import (
    SqlAlchemyStaffRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.config import get_settings
from restaurante.shared.database import get_session
from restaurante.shared.realtime.deps import EventStreamDep, get_event_publisher

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]

__all__ = [
    "CurrentDriverDep",
    "DeliveryServiceDep",
    "EventStreamDep",
    "TenantDep",
    "get_delivery_service",
]


@lru_cache
def get_geocode_queue() -> GeocodeQueue:
    """One announcer for the process — it holds a pool, so it must outlive the request."""
    return ArqGeocodeQueue(get_settings().redis_url)


class _OrderSettlementAdapter:
    """Adapta el módulo orders al puerto `OrderSettlement` de delivery.

    Aquí vive la única diferencia real entre los dos desenlaces:

    - **Entregada** — si el pedido es en efectivo y queda saldo, lo cobra a nombre del
      domiciliario y luego cierra bajo las reglas de siempre. El monto sale del pedido, no de
      lo que alguien teclee: cobrar es confirmar lo que el pedido ya decía.
    - **No entregada** — cierra en modo write-off. El cliente no recibió nada, así que lo
      impagado lo absorbe el negocio; fiárselo convertiría una entrega fallida en una deuda
      suya. El inventario se descuenta igual, porque la comida se cocinó.
    """

    def __init__(
        self,
        orders: OrderService,
        payments: PaymentService,
        repo: SqlAlchemyOrdersRepository,
    ) -> None:
        self._orders = orders
        self._payments = payments
        self._repo = repo

    async def settle_delivered(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        collected_by_employee_id: uuid.UUID | None = None,
    ) -> None:
        order = await self._repo.get_order(tenant_id, order_id)
        if order is None or order.status != "open":
            # Ya cerrada (o inexistente): resolver una entrega dos veces no debe cobrar dos.
            return
        paid = await self._repo.payments_total(tenant_id, order_id)
        remainder = order.total - paid
        if (
            remainder > 0
            and (order.payment_method or "cash") == "cash"
            and collected_by_employee_id is not None
        ):
            await self._payments.register_payment(
                tenant_id, order_id, remainder, "cash", collected_by_employee_id
            )
        await self._orders.close_order(tenant_id, order_id)

    async def settle_not_delivered(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> None:
        order = await self._repo.get_order(tenant_id, order_id)
        if order is None or order.status != "open":
            return
        # La deuda de devolución se abre ANTES de cerrar, mientras los pagos siguen a la
        # vista del pedido abierto. Sólo nace si había plata: el efectivo se cobra en la
        # puerta, así que un no entregado en efectivo nunca se pagó.
        await self._payments.open_refund_if_prepaid(tenant_id, order_id)
        await self._orders.close_order(tenant_id, order_id, write_off=True)


def build_order_settlement(session: AsyncSession) -> _OrderSettlementAdapter:
    """El adaptador delivery→orders sobre la sesión dada."""
    repo = SqlAlchemyOrdersRepository(session)
    return _OrderSettlementAdapter(
        orders=OrderService(repo=repo),
        payments=PaymentService(repo=repo),
        repo=repo,
    )


def get_delivery_service(session: SessionDep) -> DeliveryService:
    # No geocoder: the API never geocodes. An address arrives, it is stored, and the worker
    # pins it moments later — nothing here waits on a provider.
    #
    # The queue is the ONLY thing this path gained: one local Redis round-trip (~1 ms) to say
    # "this one needs a pin, now". It must never grow into the provider call it replaced —
    # that is the whole point of the record being the resolver's set and this being a hint.
    return DeliveryService(
        repo=SqlAlchemyDeliveryRepository(session),
        geocode_queue=get_geocode_queue(),
        events=get_event_publisher(),
        # Resolver una entrega cierra su comanda: entregada con su cobro, no entregada como
        # write-off. Sobre la MISMA sesión, para que cobro y cierre viajen juntos.
        settlement=build_order_settlement(session),
        # "Va en camino" y "entregado" son los dos avisos que el cliente sí espera.
        customer_notifier=build_customer_channel(session),
        # El mismo canal, para reemitir un enlace de pago que no llegó. Es el mismo objeto:
        # `AutoreplyService` cumple los dos puertos sin heredar de ninguno.
        payment_notifier=build_customer_channel(session),
    )


DeliveryServiceDep = Annotated[DeliveryService, Depends(get_delivery_service)]


async def get_current_driver(
    current_user: CurrentUserDep, session: SessionDep, tenant_id: TenantDep
) -> Employee:
    """Resolve the caller's own active `Employee` for driver actions.

    The driver identity is ALWAYS derived from the session here — no `employee_id` ever comes
    from the client. Raises 404 when the auth user is not linked to an employee.
    """
    staff = StaffService(repo=SqlAlchemyStaffRepository(session))
    return await staff.get_employee_for_user(tenant_id, current_user.id)


CurrentDriverDep = Annotated[Employee, Depends(get_current_driver)]
