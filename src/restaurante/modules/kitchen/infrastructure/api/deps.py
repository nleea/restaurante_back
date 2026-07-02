"""Dependency wiring for the Kitchen API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.kitchen.application.use_cases.manage_kitchen import (
    KitchenService,
)
from restaurante.modules.kitchen.domain.ports import KitchenEventPublisher
from restaurante.modules.kitchen.infrastructure.events import (
    RedisKitchenEventPublisher,
    RedisKitchenEventStream,
)
from restaurante.modules.kitchen.infrastructure.repositories import (
    SqlAlchemyKitchenRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.config import get_settings
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]

# Process-wide publisher: the Redis client is lazy and the port is best-effort, so sharing one
# instance across requests is safe and avoids a connection pool per request.
_event_publisher: KitchenEventPublisher | None = None


def get_event_publisher() -> KitchenEventPublisher:
    global _event_publisher
    if _event_publisher is None:
        _event_publisher = RedisKitchenEventPublisher(get_settings().redis_url)
    return _event_publisher


def get_event_stream() -> RedisKitchenEventStream:
    return RedisKitchenEventStream(get_settings().redis_url)


def get_kitchen_service(session: SessionDep) -> KitchenService:
    # Wire the orders-readiness outbound adapter over the SAME session so advancing/routing
    # tickets recomputes and persists the order's kitchen_state (and auto-dispatches delivery).
    from restaurante.modules.orders.infrastructure.api.deps import (
        build_orders_readiness,
    )

    return KitchenService(
        repo=SqlAlchemyKitchenRepository(session),
        orders_readiness=build_orders_readiness(session),
        events=get_event_publisher(),
    )


KitchenServiceDep = Annotated[KitchenService, Depends(get_kitchen_service)]
EventStreamDep = Annotated[RedisKitchenEventStream, Depends(get_event_stream)]
