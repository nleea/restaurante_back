"""Infraestructura de base de datos: engine async, sesión, Base declarativa y mixins.

`Base` y los mixins viven en la capa de infraestructura (no en el dominio puro),
porque son detalles de SQLAlchemy. El dominio no debe importar nada de aquí.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Uuid, func
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from restaurante.shared.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=settings.debug, future=True)

SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base declarativa para todos los modelos ORM."""


class TimestampMixin:
    """Añade columnas de auditoría temporal a un modelo."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantScopedMixin:
    """Marca una entidad como perteneciente a un tenant (aislamiento row-level).

    Toda entidad de negocio debe heredar de este mixin: el filtro automático de
    tenancy (ver `shared.tenancy.filtering`) sólo aplica a modelos que lo usan.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )


class BranchScopedMixin(TenantScopedMixin):
    """Marks an entity as belonging to a branch (multi-branch).

    Binding architectural decision (see CLAUDE.md): every business entity must
    carry `branch_id` from day 1 even if only a single branch is operated today,
    to avoid a painful migration when N branches are enabled.

    Inherits from `TenantScopedMixin`, so a business model only needs to inherit
    from `BranchScopedMixin` to get BOTH columns (`tenant_id` and `branch_id`)
    and, with them, the automatic tenancy filter.
    """

    branch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependencia FastAPI: entrega una sesión async por request."""
    async with SessionFactory() as session:
        yield session
