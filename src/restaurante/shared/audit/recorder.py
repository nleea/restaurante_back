"""Adaptador de persistencia para auditoría (implementa `AuditEventRecorder`).

Satisface estructuralmente el puerto `shared.domain.audit.AuditEventRecorder`
(tipado por Protocol). Persiste cada evento en su PROPIA sesión/transacción para
que auditar no acople ni contamine la transacción de negocio, y es tolerante a
fallos: un error al auditar nunca debe tumbar la operación auditada.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from restaurante.shared.audit.models import AuditLogModel
from restaurante.shared.database import SessionFactory
from restaurante.shared.domain.audit import AuditEvent

logger = logging.getLogger("restaurante.audit")


class SqlAlchemyAuditRecorder:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] | None = None
    ) -> None:
        # Sesión independiente: la auditoría no comparte la unidad de trabajo
        # del caso de uso (un rollback de negocio no debe borrar el rastro).
        self._session_factory = session_factory or SessionFactory

    async def record(self, event: AuditEvent) -> None:
        try:
            async with self._session_factory() as session:
                session.add(
                    AuditLogModel(
                        tenant_id=event.tenant_id,
                        actor_id=event.actor_id,
                        branch_id=event.branch_id,
                        action=event.action,
                        entity_type=event.entity_type,
                        entity_id=event.entity_id,
                        ip=event.ip,
                        detail=event.detail,
                    )
                )
                await session.commit()
        except Exception:  # pragma: no cover - defensa: auditar nunca debe romper
            # Nunca propagamos: la operación de negocio prima sobre el rastro.
            logger.exception("No se pudo registrar el evento de auditoría %s", event.action)
