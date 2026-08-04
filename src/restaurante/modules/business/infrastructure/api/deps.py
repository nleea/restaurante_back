"""Dependency wiring for the Business API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.business.application.use_cases.manage_business import (
    BusinessService,
)
from restaurante.modules.business.infrastructure.repositories import (
    SqlAlchemyBusinessRepository,
)
from restaurante.modules.menu.application.use_cases.manage_appearance import (
    AppearanceService,
)
from restaurante.modules.menu.infrastructure.repositories import (
    SqlAlchemyMenuRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_business_service(session: SessionDep) -> BusinessService:
    # Appearance wired so a profile photo update writes the shared brand logo.
    return BusinessService(
        repo=SqlAlchemyBusinessRepository(session),
        appearance=AppearanceService(repo=SqlAlchemyMenuRepository(session)),
    )


BusinessServiceDep = Annotated[BusinessService, Depends(get_business_service)]
