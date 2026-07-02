"""Auditoría como capacidad transversal del dominio (no es un módulo de negocio).

Decisión vinculante (CLAUDE.md): Auditoría/Logs es cross-cutting; es barato si se
planea en el modelo de datos desde el inicio y caro de retrofitear. Aquí vive el
contrato puro (sin framework): un evento de auditoría y el puerto que lo registra.
Los adaptadores concretos (SQLAlchemy) lo implementan en `shared.audit`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AuditEvent:
    """Un hecho auditable: quién hizo qué, cuándo (lo fija el almacén) y desde dónde.

    - `action`: dotted event verb (e.g. ``login.success``).
    - `entity_type` / `entity_id`: the affected entity, if any.
    - `actor_id`: the user that originated the event, if known.
    - `branch_id`: the branch, if the event occurs in its context.
    - `ip`: network origin, if available.
    - `detail`: brief NON-sensitive extra context (never passwords/tokens).
    """

    tenant_id: uuid.UUID
    action: str
    actor_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    ip: str | None = None
    detail: str | None = None


class AuditEventRecorder(Protocol):
    """Puerto para registrar eventos de auditoría.

    La capa de aplicación depende de esta interfaz, no de SQLAlchemy. Las
    implementaciones deben ser tolerantes: auditar nunca debe tumbar la operación
    de negocio que se está auditando.
    """

    async def record(self, event: AuditEvent) -> None: ...
