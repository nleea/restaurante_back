"""ORM models of the identity module.

Holds the access/identity tables: `persons` (pure human data), `users` (login),
`roles`, `permissions` and the `role_permissions` bridge.

Tenancy notes:
- `persons` and `permissions` are global (shared across tenants), like catalogs.
- `roles` may be global (`is_global=True`, `tenant_id` NULL) or tenant-owned, so
  `tenant_id` is nullable and the model cannot use `TenantScopedMixin`.
- `users` stay tenant-scoped (existing behaviour, unchanged).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import Base, TenantScopedMixin, TimestampMixin


class PersonModel(Base, TimestampMixin):
    """Pure human data (maps from `persona`).

    Knows nothing about login or tenancy. A person can be a customer and/or an
    employee at the same time, possibly across businesses, so it is global.
    """

    __tablename__ = "persons"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    document_number: Mapped[str | None] = mapped_column(
        String(30), unique=True, nullable=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    second_last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    city_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("cities.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class UserModel(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Aligned additively to the source schema (`usuario`). `person_id`/`username`
    # are nullable so already-seeded users (created without a person) stay valid;
    # the source marks them NOT NULL / UNIQUE.
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("persons.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    username: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PermissionModel(Base):
    """Fixed system catalog of actions (maps from `permiso`). Global."""

    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    module: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class RoleModel(Base, TimestampMixin):
    """Role (maps from `rol`).

    System base roles have `tenant_id` NULL and `is_global=True`; each tenant may
    also create its own roles. Because `tenant_id` is nullable, this model does
    not use `TenantScopedMixin` (and is therefore not auto-filtered); repositories
    must scope queries with `tenant_id == X OR is_global`.
    """

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_global: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RolePermissionModel(Base):
    """Bridge: which permissions a role has (maps from `rol_permiso`)."""

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint(
            "role_id", "permission_id", name="uq_role_permissions_role_permission"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class UserRoleModel(Base, TenantScopedMixin, TimestampMixin):
    """Bridge: which roles are assigned to a user (RBAC source of truth).

    Decoupled from the HR record (`employees.role_id`): any user (admin, API,
    staff) gets its roles here. Tenant-scoped, so the assignment belongs to the
    tenant even when the role itself is a global base role.
    """

    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )


class UserPermissionModel(Base, TenantScopedMixin, TimestampMixin):
    """Per-user permission override (maps the dynamic 'change what a user can do').

    `effect` is `allow` (grant beyond the roles) or `deny` (revoke despite the
    roles). Effective permissions = (role permissions ∪ allow) − deny.
    """

    __tablename__ = "user_permissions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "permission_id", name="uq_user_permissions_user_permission"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    effect: Mapped[str] = mapped_column(String(10), nullable=False)
