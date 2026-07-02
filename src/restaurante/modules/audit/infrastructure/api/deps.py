"""Dependency wiring for the Audit query API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.audit.application.use_cases.query_audit import (
    AuditQueryService,
)
from restaurante.modules.audit.infrastructure.repositories import (
    SqlAlchemyAuditQueryRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_audit_service(session: SessionDep) -> AuditQueryService:
    return AuditQueryService(repo=SqlAlchemyAuditQueryRepository(session))


AuditServiceDep = Annotated[AuditQueryService, Depends(get_audit_service)]
