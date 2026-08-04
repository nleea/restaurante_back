"""Dependency wiring for the Guest Profile API.

The read/create/update surface depends ONLY on ``TenantDep`` (tenant by
subdomain) — no ``require_permission`` — because a guest is not logged in. The
``claim`` endpoint additionally requires ``CurrentUserDep``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.guest_profile.application.use_cases.manage_guest_profile import (
    GuestProfileService,
)
from restaurante.modules.guest_profile.infrastructure.repositories import (
    SqlAlchemyGuestProfileRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_guest_profile_service(session: SessionDep) -> GuestProfileService:
    return GuestProfileService(repo=SqlAlchemyGuestProfileRepository(session))


GuestProfileServiceDep = Annotated[
    GuestProfileService, Depends(get_guest_profile_service)
]
