"""Dependency wiring for the Orders API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.delivery.application.use_cases.manage_delivery import (
    DeliveryService,
)
from restaurante.modules.delivery.infrastructure.repositories import (
    SqlAlchemyDeliveryRepository,
)
from restaurante.modules.kitchen.application.use_cases.manage_kitchen import KitchenService
from restaurante.modules.kitchen.infrastructure.repositories import (
    SqlAlchemyKitchenRepository,
)
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
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.config import get_settings
from restaurante.shared.database import get_session
from restaurante.shared.domain.errors import ConflictError
from restaurante.shared.realtime.deps import EventStreamDep, get_event_publisher

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]

__all__ = [
    "EventStreamDep",
    "OrderServiceDep",
    "PaymentServiceDep",
    "TenantDep",
    "build_orders_readiness",
    "get_order_service",
    "get_payment_service",
]


class _KitchenRoutingAdapter:
    """Adapts the kitchen routing service to the orders `KitchenRouting` outbound port. Lives at the
    composition root so the orders application never imports the kitchen module directly."""

    def __init__(self, kitchen: KitchenService) -> None:
        self._kitchen = kitchen

    async def route_order(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> None:
        await self._kitchen.route_order(tenant_id, order_id)


class _DeliveryDispatchAdapter:
    """Adapts the delivery service to the orders `DeliveryDispatch` outbound port. Idempotent: a
    delivery record that already exists is left untouched (create raises `ConflictError`)."""

    def __init__(self, delivery: DeliveryService) -> None:
        self._delivery = delivery

    async def ensure_delivery_for_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> None:
        """Last resort: make sure a ready delivery order is visible to Dispatch.

        The normal path is now the Salón/comanda, which creates the record WITH the address
        (and therefore a geocoded pin) the moment the order is taken — every role that can
        open an order holds `delivery.address`. This hook then hits the duplicate conflict
        and does nothing.

        It still fires for orders opened before that existed, for a capture that failed, and
        for orders created straight through the API. The empty address is deliberate: a
        blank record in Dispatch shouting "give me an address" beats a ready delivery order
        that is invisible there and never leaves. Note it bypasses `CreateDeliveryRequest`
        (which requires `min_length=1`), so it can write a row the public API would reject —
        that is the point, and the reason it is the only caller allowed to.
        """
        try:
            await self._delivery.create_delivery(tenant_id, order_id, address_text="")
        except ConflictError:
            # The order already has a delivery record — the address was captured at open.
            pass

    async def release_delivery_for_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> None:
        """La otra dirección: la comanda se acabó, suelta lo que tenía cogido.

        Sólo afecta a la entrega que nunca salió; el servicio decide eso. Idempotente: sin
        entrega, o con una ya resuelta, no cambia nada.
        """
        await self._delivery.release_delivery_for_order(tenant_id, order_id)


class _OrdersReadinessAdapter:
    """Adapts an OrderService to the kitchen `OrdersReadiness` outbound port, persisting the
    order's derived `kitchen_state` and triggering delivery auto-dispatch on `ready`."""

    def __init__(self, orders: OrderService) -> None:
        self._orders = orders

    async def set_order_kitchen_state(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, state: str
    ) -> None:
        await self._orders.set_kitchen_state(tenant_id, order_id, state)


def _delivery_dispatch(session: AsyncSession) -> _DeliveryDispatchAdapter:
    # Events wired here too: when auto-dispatch creates the delivery record on `ready`, the
    # dispatch board should light up like any other create.
    return _DeliveryDispatchAdapter(
        DeliveryService(
            repo=SqlAlchemyDeliveryRepository(session), events=get_event_publisher()
        )
    )


def build_orders_readiness(session: AsyncSession) -> _OrdersReadinessAdapter:
    """Build the kitchen→orders readiness adapter over the given session. Reused by the kitchen
    composition root so KDS advances/routes persist `Order.kitchen_state` and auto-dispatch."""
    readiness_orders = OrderService(
        repo=SqlAlchemyOrdersRepository(session),
        delivery_dispatch=_delivery_dispatch(session),
        # Este es el camino por el que un pedido llega a `ready`, así que es el único que
        # puede avisar "listo para recoger" (apagado de fábrica).
        customer_notifier=build_customer_channel(session),
    )
    return _OrdersReadinessAdapter(readiness_orders)


def get_order_service(session: SessionDep) -> OrderService:
    # Reuse the kitchen routing over the SAME request session so the just-added item is visible
    # and its tickets are created in the same request. The kitchen service is wired with the
    # readiness adapter so auto-routing recomputes and persists the order's kitchen_state.
    kitchen_routing = _KitchenRoutingAdapter(
        KitchenService(
            repo=SqlAlchemyKitchenRepository(session),
            orders_readiness=build_orders_readiness(session),
        )
    )
    return OrderService(
        repo=SqlAlchemyOrdersRepository(session),
        kitchen_routing=kitchen_routing,
        events=get_event_publisher(),
        customer_notifier=build_customer_channel(session),
        # Este es el servicio que atiende cancelar y cerrar, así que es el que tiene que poder
        # soltar la entrega. Sin el puerto aquí, `_release_delivery` sale por la primera línea
        # y la entrega se queda bloqueando la caja — que es exactamente el bug de origen.
        delivery_dispatch=_delivery_dispatch(session),
        # El dominio público de la carta, para poder construir el QR de una mesa. Se lee aquí
        # y no dentro del caso de uso, igual que hace messaging con el mismo ajuste.
        storefront_base_url=get_settings().storefront_base_url,
    )


OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]


class _OrdersPaymentGateAdapter:
    """Adapts the payment side to the kitchen `OrdersPaymentGate` port.

    Built WITHOUT kitchen routing on purpose: this adapter only answers a question for the
    kitchen. Giving it the routing port would close a cycle (kitchen → orders → kitchen).
    """

    def __init__(self, payments: PaymentService, repo: SqlAlchemyOrdersRepository) -> None:
        self._payments = payments
        self._repo = repo

    async def may_cook(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> bool:
        order = await self._repo.get_order(tenant_id, order_id)
        if order is None:
            # The kitchen raises its own not-found for a missing order; don't shadow it here.
            return True
        return await self._payments.is_payment_verified(tenant_id, order)


def build_orders_payment_gate(session: AsyncSession) -> _OrdersPaymentGateAdapter:
    """The kitchen→orders payment gate over the given session."""
    repo = SqlAlchemyOrdersRepository(session)
    return _OrdersPaymentGateAdapter(PaymentService(repo=repo), repo)


def get_payment_service(session: SessionDep) -> PaymentService:
    # Import local: el composition root es el ÚNICO sitio donde orders puede ver delivery, y a
    # nivel de módulo esto crearía un ciclo (delivery ya importa el servicio de pagos).
    from restaurante.modules.delivery.infrastructure.quote_gate import (
        SqlAlchemyDeliveryQuoteGate,
    )

    # Wired with kitchen routing so verifying a prepaid payment also fires the order — one
    # gesture for what is one moment: "el comprobante está bien, que lo cocinen".
    return PaymentService(
        repo=SqlAlchemyOrdersRepository(session),
        kitchen_routing=_KitchenRoutingAdapter(
            KitchenService(repo=SqlAlchemyKitchenRepository(session))
        ),
        # Para que resolver un comprobante se lo diga al cliente. Es el mismo canal que ya avisa
        # "recibimos tu pedido"; sin él, el cliente manda la foto a un buzón mudo.
        customer_notifier=build_customer_channel(session),
        # Y la puerta del domicilio: un pedido cuyo domicilio aún no se ha cotizado tiene un
        # total que no incluye el domicilio, así que verificarlo cobraría de menos y mandaría la
        # comida a cocina. Importado aquí dentro para no atar `orders` a `delivery` en el módulo.
        quote_gate=SqlAlchemyDeliveryQuoteGate(session),
    )


PaymentServiceDep = Annotated[PaymentService, Depends(get_payment_service)]
