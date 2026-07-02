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
from restaurante.modules.orders.application.use_cases.manage_orders import OrderService
from restaurante.modules.orders.application.use_cases.manage_payments import (
    PaymentService,
)
from restaurante.modules.orders.infrastructure.repositories import (
    SqlAlchemyOrdersRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session
from restaurante.shared.domain.errors import ConflictError

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


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
        try:
            # The order carries no address of its own; Dispatch can complete it later. An empty
            # address keeps the record creatable so the order enters Dispatch as `pending`.
            await self._delivery.create_delivery(tenant_id, order_id, address_text="")
        except ConflictError:
            # Idempotent: the order already has a delivery record — nothing to do.
            pass


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
    return _DeliveryDispatchAdapter(
        DeliveryService(repo=SqlAlchemyDeliveryRepository(session))
    )


def build_orders_readiness(session: AsyncSession) -> _OrdersReadinessAdapter:
    """Build the kitchen→orders readiness adapter over the given session. Reused by the kitchen
    composition root so KDS advances/routes persist `Order.kitchen_state` and auto-dispatch."""
    readiness_orders = OrderService(
        repo=SqlAlchemyOrdersRepository(session),
        delivery_dispatch=_delivery_dispatch(session),
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
        repo=SqlAlchemyOrdersRepository(session), kitchen_routing=kitchen_routing
    )


OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]


def get_payment_service(session: SessionDep) -> PaymentService:
    return PaymentService(repo=SqlAlchemyOrdersRepository(session))


PaymentServiceDep = Annotated[PaymentService, Depends(get_payment_service)]
