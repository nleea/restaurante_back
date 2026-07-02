"""Dependency wiring for the Finance API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.finance.application.use_cases.manage_finance import (
    FinanceService,
)
from restaurante.modules.finance.infrastructure.repositories import (
    SqlAlchemyFinanceRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_finance_service(session: SessionDep) -> FinanceService:
    return FinanceService(repo=SqlAlchemyFinanceRepository(session))


FinanceServiceDep = Annotated[FinanceService, Depends(get_finance_service)]
