"""Dependency wiring for the Purchasing API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.purchasing.application.use_cases.manage_purchasing import (
    PurchasingService,
)
from restaurante.modules.purchasing.infrastructure.repositories import (
    SqlAlchemyPurchasingRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_purchasing_service(session: SessionDep) -> PurchasingService:
    return PurchasingService(repo=SqlAlchemyPurchasingRepository(session))


PurchasingServiceDep = Annotated[PurchasingService, Depends(get_purchasing_service)]
