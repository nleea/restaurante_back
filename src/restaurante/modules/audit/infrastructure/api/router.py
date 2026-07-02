"""Audit API: read-only querying of the cross-cutting audit log.

RBAC: all endpoints require `audit.read`. No write endpoints — the log is
append-only and authored by the internal recorder.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from restaurante.modules.audit.infrastructure.api.deps import (
    AuditServiceDep,
    TenantDep,
)
from restaurante.modules.audit.infrastructure.api.schemas import AuditLogEntryResponse
from restaurante.modules.identity.infrastructure.api.deps import require_permission

router = APIRouter(prefix="/audit", tags=["audit"])

_READ = Depends(require_permission("audit.read"))


@router.get("/logs", response_model=list[AuditLogEntryResponse], dependencies=[_READ])
async def list_audit_logs(
    service: AuditServiceDep,
    tenant_id: TenantDep,
    action: str | None = None,
    actor_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditLogEntryResponse]:
    entries = await service.list_entries(
        tenant_id,
        action=action,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        branch_id=branch_id,
        limit=limit,
        offset=offset,
    )
    return [
        AuditLogEntryResponse.model_validate(e, from_attributes=True) for e in entries
    ]


@router.get(
    "/logs/{entry_id}",
    response_model=AuditLogEntryResponse,
    dependencies=[_READ],
)
async def get_audit_log(
    entry_id: uuid.UUID, service: AuditServiceDep, tenant_id: TenantDep
) -> AuditLogEntryResponse:
    entry = await service.get_entry(tenant_id, entry_id)
    return AuditLogEntryResponse.model_validate(entry, from_attributes=True)
