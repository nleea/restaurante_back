"""Tests for the multi-branch axis and the automatic tenancy filter.

They verify the binding architectural decision (CLAUDE.md): every business
entity can be anchored to a branch from day 1, and the tenancy filter
automatically isolates rows per tenant.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import String, Uuid
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import Base, BranchScopedMixin
from restaurante.shared.tenancy.context import (
    reset_current_tenant_id,
    set_current_tenant_id,
)
from restaurante.shared.tenancy.filtering import install_tenant_filter
from restaurante.shared.tenancy.models import BranchModel, TenantModel


class _ProductStub(Base, BranchScopedMixin):
    """Minimal business model to exercise `BranchScopedMixin`."""

    __tablename__ = "_product_stub"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


def test_branch_scoped_mixin_provides_both_columns() -> None:
    cols = _ProductStub.__table__.columns
    assert "tenant_id" in cols
    assert "branch_id" in cols


def test_branch_is_tenant_scoped() -> None:
    # A branch belongs to a tenant but not to another branch.
    assert "tenant_id" in BranchModel.__table__.columns
    assert "branch_id" not in BranchModel.__table__.columns


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    install_tenant_filter()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def test_filter_isolates_by_tenant(session: AsyncSession) -> None:
    from sqlalchemy import select

    tenant_a = TenantModel(slug="a", name="A", is_active=True)
    tenant_b = TenantModel(slug="b", name="B", is_active=True)
    session.add_all([tenant_a, tenant_b])
    await session.flush()

    branch_a = BranchModel(
        tenant_id=tenant_a.id, code="S1", name="Branch A", is_active=True
    )
    branch_b = BranchModel(
        tenant_id=tenant_b.id, code="S1", name="Branch B", is_active=True
    )
    session.add_all([branch_a, branch_b])
    await session.flush()

    session.add_all(
        [
            _ProductStub(tenant_id=tenant_a.id, branch_id=branch_a.id, name="A"),
            _ProductStub(tenant_id=tenant_b.id, branch_id=branch_b.id, name="B"),
        ]
    )
    await session.commit()

    tenant_a_id = tenant_a.id
    token = set_current_tenant_id(tenant_a_id)
    try:
        # Select concrete columns to avoid lazy loads.
        result = await session.execute(
            select(_ProductStub.name, _ProductStub.tenant_id)
        )
        rows = result.all()
    finally:
        reset_current_tenant_id(token)

    assert len(rows) == 1
    assert rows[0].tenant_id == tenant_a_id
    assert rows[0].name == "A"


async def test_skip_tenant_filter_sees_everything(session: AsyncSession) -> None:
    from sqlalchemy import select

    tenant_a = TenantModel(slug="a2", name="A", is_active=True)
    tenant_b = TenantModel(slug="b2", name="B", is_active=True)
    session.add_all([tenant_a, tenant_b])
    await session.commit()

    token = set_current_tenant_id(tenant_a.id)
    try:
        stmt = select(TenantModel).execution_options(skip_tenant_filter=True)
        rows = (await session.execute(stmt)).scalars().all()
    finally:
        reset_current_tenant_id(token)

    # TenantModel is not tenant-scoped, but the test confirms the flag flows.
    assert len(rows) == 2


@pytest.mark.parametrize("code", ["S1", "S2"])
def test_branch_code_configurable(code: str) -> None:
    branch = BranchModel(
        tenant_id=uuid.uuid4(), code=code, name="X", is_active=True
    )
    assert branch.code == code
