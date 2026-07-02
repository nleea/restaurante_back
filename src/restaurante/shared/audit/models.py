"""Audit log ORM model (cross-cutting capability).

`AuditLogModel` is tenant-scoped (every row belongs to a tenant, and the
automatic tenancy filter isolates it). `branch_id` is OPTIONAL: there are
cross-cutting events (e.g. a login) that occur before a branch is known.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import Base, TenantScopedMixin, TimestampMixin


class AuditLogModel(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Who originated the event (may be unknown, e.g. a failed login).
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    # Branch in whose context the event occurs (optional for cross-cutting events).
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # What happened: dotted verb (e.g. ``login.success``) and affected entity.
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # Where from and brief NON-sensitive context.
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
