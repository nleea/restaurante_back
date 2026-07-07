"""Dependency wiring for the Reports API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.reports.application.use_cases.reporting import ReportsService
from restaurante.modules.reports.infrastructure.repositories import (
    SqlAlchemyReportsRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_reports_service(session: SessionDep) -> ReportsService:
    return ReportsService(repo=SqlAlchemyReportsRepository(session))


ReportsServiceDep = Annotated[ReportsService, Depends(get_reports_service)]
