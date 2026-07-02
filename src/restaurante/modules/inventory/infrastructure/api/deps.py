"""Dependency wiring for the Inventory API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.inventory.application.use_cases.manage_inventory import (
    InventoryService,
)
from restaurante.modules.inventory.infrastructure.repositories import (
    SqlAlchemyInventoryRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_inventory_service(session: SessionDep) -> InventoryService:
    return InventoryService(repo=SqlAlchemyInventoryRepository(session))


InventoryServiceDep = Annotated[InventoryService, Depends(get_inventory_service)]
