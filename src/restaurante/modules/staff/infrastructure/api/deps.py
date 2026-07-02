"""Dependency wiring for the Staff API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.staff.application.use_cases.manage_staff import StaffService
from restaurante.modules.staff.infrastructure.repositories import (
    SqlAlchemyStaffRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_staff_service(session: SessionDep) -> StaffService:
    return StaffService(repo=SqlAlchemyStaffRepository(session))


StaffServiceDep = Annotated[StaffService, Depends(get_staff_service)]
