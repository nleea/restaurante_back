"""ORM model of the Guest Profile module.

Tenant-scoped table keyed by an opaque ``token`` (the cookie value). Optionally
links to a login ``user`` once the guest authenticates. No personal data ever
leaves the row via the cookie — only the token does.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import Base, TenantScopedMixin, TimestampMixin


class GuestProfileModel(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "guest_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    token: Mapped[uuid.UUID] = mapped_column(
        Uuid, nullable=False, unique=True, index=True
    )
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
