"""Structural tenancy ORM models: tenant and branch.

`TenantModel` is the isolation root (not tenant-scoped). `BranchModel` is
tenant-scoped (belongs to a tenant) but is the base of the multi-branch axis:
business entities reference `branches.id` via `BranchScopedMixin`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import Base, TenantScopedMixin, TimestampMixin


class TenantModel(Base, TimestampMixin):
    """The tenant: a business (maps from `negocio`). Isolation root.

    Carries the subdomain (`slug`) plus business profile fields. The profile
    fields are nullable so existing/seeded tenants and tests remain valid; they
    can be tightened once onboarding always provides them.
    """

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # The slug is the subdomain: <slug>.<base_domain>
    slug: Mapped[str] = mapped_column(String(63), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Business profile (from `negocio`). `tax_id` maps the Colombian NIT.
    tax_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    city_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("cities.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class BranchModel(Base, TenantScopedMixin, TimestampMixin):
    """Branch of a tenant.

    Multi-branch axis of the data model. Even if a restaurant operates a single
    branch today, every business entity anchors to `branches.id` from the start
    (see `BranchScopedMixin`). The pair (`tenant_id`, `code`) is unique to allow a
    human-readable identifier per tenant.
    """

    __tablename__ = "branches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_branches_tenant_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # `tenant_id` comes from TenantScopedMixin, but we redeclare it so the FK
    # points explicitly to tenants (branches are not deleted on cascade).
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # `city_id` is nullable so the existing seed/tests (which create no city)
    # keep working; the source schema (`sucursal`) marks it NOT NULL.
    city_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("cities.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
