"""Read-only persistence adapter for the Audit query module.

Reads the cross-cutting ``shared.audit.models.AuditLogModel``; filters explicitly
by ``tenant_id``. The `action` filter matches an exact value or a dotted prefix
(``login`` → ``login.success``/``login.failure``).
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.audit.domain.entities import AuditLogEntry
from restaurante.shared.audit.models import AuditLogModel


def _entry(m: AuditLogModel) -> AuditLogEntry:
    return AuditLogEntry(
        id=m.id,
        tenant_id=m.tenant_id,
        action=m.action,
        actor_id=m.actor_id,
        branch_id=m.branch_id,
        entity_type=m.entity_type,
        entity_id=m.entity_id,
        ip=m.ip,
        detail=m.detail,
        created_at=m.created_at,
    )


class SqlAlchemyAuditQueryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_entries(
        self,
        tenant_id: uuid.UUID,
        *,
        action: str | None = None,
        actor_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        limit: int,
        offset: int,
    ) -> list[AuditLogEntry]:
        stmt = select(AuditLogModel).where(AuditLogModel.tenant_id == tenant_id)
        if action is not None:
            stmt = stmt.where(
                or_(
                    AuditLogModel.action == action,
                    AuditLogModel.action.like(f"{action}.%"),
                )
            )
        if actor_id is not None:
            stmt = stmt.where(AuditLogModel.actor_id == actor_id)
        if entity_type is not None:
            stmt = stmt.where(AuditLogModel.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(AuditLogModel.entity_id == entity_id)
        if branch_id is not None:
            stmt = stmt.where(AuditLogModel.branch_id == branch_id)
        stmt = stmt.order_by(AuditLogModel.created_at.desc()).limit(limit).offset(offset)
        return [_entry(m) for m in (await self._session.execute(stmt)).scalars()]

    async def get_entry(
        self, tenant_id: uuid.UUID, entry_id: uuid.UUID
    ) -> AuditLogEntry | None:
        stmt = select(AuditLogModel).where(
            AuditLogModel.id == entry_id, AuditLogModel.tenant_id == tenant_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _entry(model) if model else None
