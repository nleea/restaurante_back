"""Domain entities of the Identity and Access module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class PermissionEffect(str, Enum):
    """Effect of a per-user permission override."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass
class Person:
    """Pure human data (maps from `persona`). Framework-free."""

    id: uuid.UUID
    first_name: str
    last_name: str
    document_type: str | None = None
    document_number: str | None = None
    middle_name: str | None = None
    second_last_name: str | None = None
    phone: str | None = None
    email: str | None = None
    city_id: uuid.UUID | None = None
    address: str | None = None
    birth_date: date | None = None


@dataclass
class User:
    """User belonging to a tenant.

    Pure entity: knows nothing about SQLAlchemy or FastAPI. The password only
    exists here in its already-hashed form. `person_id`/`username`/`last_login_at`
    are optional to stay compatible with users created before the schema grew.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    hashed_password: str
    name: str
    is_active: bool
    person_id: uuid.UUID | None = None
    username: str | None = None
    last_login_at: datetime | None = None


@dataclass
class Permission:
    """A fixed system action (maps from `permiso`)."""

    id: uuid.UUID
    code: str
    name: str
    module: str
    description: str | None = None


@dataclass
class Role:
    """A role (maps from `rol`). `tenant_id` is None for global system roles."""

    id: uuid.UUID
    name: str
    is_global: bool
    is_active: bool
    tenant_id: uuid.UUID | None = None
    description: str | None = None


@dataclass
class RolePermission:
    """Bridge role <-> permission (maps from `rol_permiso`)."""

    id: uuid.UUID
    role_id: uuid.UUID
    permission_id: uuid.UUID


@dataclass
class UserRole:
    """A role assigned to a user (RBAC source of truth)."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID


@dataclass
class UserPermissionOverride:
    """A per-user grant/deny on top of the user's roles."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    permission_id: uuid.UUID
    effect: PermissionEffect
