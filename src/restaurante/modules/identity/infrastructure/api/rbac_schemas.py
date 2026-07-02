"""Pydantic schemas for the RBAC management API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from restaurante.modules.identity.domain.entities import PermissionEffect


class UserSummaryResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    username: str | None = None
    is_active: bool
    last_login_at: datetime | None = None


class PermissionResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    module: str
    description: str | None = None


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    is_global: bool
    is_active: bool
    tenant_id: uuid.UUID | None = None


class CreateRoleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)


class CreateUserRequest(BaseModel):
    """Provision a tenant user with an inline person (and optional initial role)."""

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    document_number: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=30)
    role_id: uuid.UUID | None = None


class ProvisionedUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    is_active: bool
    person_id: uuid.UUID


class RolePermissionsResponse(BaseModel):
    role_id: uuid.UUID
    permissions: list[str]


class SetRolePermissionsRequest(BaseModel):
    permissions: list[str]


class OverrideResponse(BaseModel):
    permission_id: uuid.UUID
    effect: PermissionEffect


class SetOverrideRequest(BaseModel):
    effect: PermissionEffect


class UserAccessResponse(BaseModel):
    user_id: uuid.UUID
    roles: list[RoleResponse]
    effective_permissions: list[str]
    overrides: list[OverrideResponse]
