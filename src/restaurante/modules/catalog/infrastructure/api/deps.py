"""Dependency wiring for the Catalog API.

Catalog data is global; `TenantDep` is included only to require an authenticated,
tenant-resolved context (consistent with the rest of the API).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.catalog.application.use_cases.manage_catalog import (
    CatalogService,
)
from restaurante.modules.catalog.infrastructure.repositories import (
    SqlAlchemyCatalogRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_catalog_service(session: SessionDep) -> CatalogService:
    return CatalogService(repo=SqlAlchemyCatalogRepository(session))


CatalogServiceDep = Annotated[CatalogService, Depends(get_catalog_service)]
