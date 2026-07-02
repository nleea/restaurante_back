"""Dependency wiring for the Delivery API."""

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
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_delivery_service(session: SessionDep) -> DeliveryService:
    return DeliveryService(repo=SqlAlchemyDeliveryRepository(session))


DeliveryServiceDep = Annotated[DeliveryService, Depends(get_delivery_service)]
