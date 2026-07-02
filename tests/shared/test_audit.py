"""Tests for the cross-cutting audit: model, adapter and port."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from restaurante.shared.audit.models import AuditLogModel
from restaurante.shared.audit.recorder import SqlAlchemyAuditRecorder
from restaurante.shared.database import Base
from restaurante.shared.domain.audit import AuditEvent


def test_audit_log_is_tenant_scoped_with_optional_branch() -> None:
    cols = AuditLogModel.__table__.columns
    assert "tenant_id" in cols
    assert cols["tenant_id"].nullable is False
    assert "branch_id" in cols
    assert cols["branch_id"].nullable is True  # cross-cutting events (login)
    assert "action" in cols


@pytest_asyncio.fixture
async def factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


async def test_recorder_persists_event(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    recorder = SqlAlchemyAuditRecorder(session_factory=factory)

    await recorder.record(
        AuditEvent(
            tenant_id=tenant_id,
            action="login.success",
            actor_id=actor_id,
            entity_type="user",
            entity_id=actor_id,
            ip="203.0.113.5",
        )
    )

    async with factory() as session:
        rows = (await session.execute(select(AuditLogModel))).scalars().all()

    assert len(rows) == 1
    assert rows[0].tenant_id == tenant_id
    assert rows[0].action == "login.success"
    assert rows[0].actor_id == actor_id
    assert rows[0].ip == "203.0.113.5"
    assert rows[0].branch_id is None


async def test_recorder_does_not_propagate_errors() -> None:
    """Auditing must never bring down the audited operation."""

    class _BrokenFactory:
        def __call__(self) -> object:
            raise RuntimeError("DB down")

    recorder = SqlAlchemyAuditRecorder(session_factory=_BrokenFactory())  # type: ignore[arg-type]
    # Must not raise despite the internal failure.
    await recorder.record(AuditEvent(tenant_id=uuid.uuid4(), action="x"))
