"""Dependency wiring for the Cash API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.cash.application.use_cases.manage_cash import CashService
from restaurante.modules.cash.infrastructure.repositories import (
    SqlAlchemyCashRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_cash_service(session: SessionDep) -> CashService:
    return CashService(repo=SqlAlchemyCashRepository(session))


CashServiceDep = Annotated[CashService, Depends(get_cash_service)]
