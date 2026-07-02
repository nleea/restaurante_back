"""RBAC management endpoints.

All routes require the `rbac.manage` permission (enforced at the router level),
so only privileged users can give/remove permissions and assign roles.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status

from restaurante.modules.identity.infrastructure.api.deps import (
    ProvisionUserDep,
    RbacServiceDep,
    TenantDep,
    require_permission,
)
from restaurante.modules.identity.infrastructure.api.rbac_schemas import (
    CreateRoleRequest,
    CreateUserRequest,
    OverrideResponse,
    PermissionResponse,
    ProvisionedUserResponse,
    RolePermissionsResponse,
    RoleResponse,
    SetOverrideRequest,
    SetRolePermissionsRequest,
    UserAccessResponse,
    UserSummaryResponse,
)

router = APIRouter(
    prefix="/rbac",
    tags=["rbac"],
    dependencies=[Depends(require_permission("rbac.manage"))],
)


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(service: RbacServiceDep) -> list[PermissionResponse]:
    return [PermissionResponse.model_validate(p, from_attributes=True)
            for p in await service.list_permissions()]


@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(service: RbacServiceDep, tenant_id: TenantDep) -> list[RoleResponse]:
    return [RoleResponse.model_validate(r, from_attributes=True)
            for r in await service.list_roles(tenant_id)]


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: CreateRoleRequest, service: RbacServiceDep, tenant_id: TenantDep
) -> RoleResponse:
    role = await service.create_role(tenant_id, payload.name, payload.description)
    return RoleResponse.model_validate(role, from_attributes=True)


@router.get("/roles/{role_id}/permissions", response_model=RolePermissionsResponse)
async def get_role_permissions(
    role_id: uuid.UUID, service: RbacServiceDep, tenant_id: TenantDep
) -> RolePermissionsResponse:
    codes = await service.get_role_permission_codes(tenant_id, role_id)
    return RolePermissionsResponse(role_id=role_id, permissions=codes)


@router.put("/roles/{role_id}/permissions", response_model=RolePermissionsResponse)
async def set_role_permissions(
    role_id: uuid.UUID,
    payload: SetRolePermissionsRequest,
    service: RbacServiceDep,
    tenant_id: TenantDep,
) -> RolePermissionsResponse:
    codes = await service.set_role_permissions(tenant_id, role_id, payload.permissions)
    return RolePermissionsResponse(role_id=role_id, permissions=codes)


@router.post(
    "/roles/{role_id}/permissions/{code}", status_code=status.HTTP_204_NO_CONTENT
)
async def add_role_permission(
    role_id: uuid.UUID, code: str, service: RbacServiceDep, tenant_id: TenantDep
) -> Response:
    await service.add_role_permission(tenant_id, role_id, code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/roles/{role_id}/permissions/{code}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_role_permission(
    role_id: uuid.UUID, code: str, service: RbacServiceDep, tenant_id: TenantDep
) -> Response:
    await service.remove_role_permission(tenant_id, role_id, code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/users",
    response_model=ProvisionedUserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    payload: CreateUserRequest,
    use_case: ProvisionUserDep,
    tenant_id: TenantDep,
) -> ProvisionedUserResponse:
    result = await use_case.execute(
        tenant_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        password=payload.password,
        document_number=payload.document_number,
        phone=payload.phone,
        role_id=payload.role_id,
    )
    return ProvisionedUserResponse(
        id=result.id,
        email=result.email,
        name=result.name,
        is_active=result.is_active,
        person_id=result.person_id,
    )


@router.get("/users", response_model=list[UserSummaryResponse])
async def list_users(
    service: RbacServiceDep, tenant_id: TenantDep
) -> list[UserSummaryResponse]:
    return [
        UserSummaryResponse.model_validate(u, from_attributes=True)
        for u in await service.list_tenant_users(tenant_id)
    ]


@router.get("/users/{user_id}/access", response_model=UserAccessResponse)
async def get_user_access(
    user_id: uuid.UUID, service: RbacServiceDep, tenant_id: TenantDep
) -> UserAccessResponse:
    access = await service.get_user_access(tenant_id, user_id)
    return UserAccessResponse(
        user_id=user_id,
        roles=[RoleResponse.model_validate(r, from_attributes=True) for r in access.roles],
        effective_permissions=access.effective_codes,
        overrides=[
            OverrideResponse(permission_id=o.permission_id, effect=o.effect)
            for o in access.overrides
        ],
    )


@router.post(
    "/users/{user_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def assign_user_role(
    user_id: uuid.UUID, role_id: uuid.UUID, service: RbacServiceDep, tenant_id: TenantDep
) -> Response:
    await service.assign_user_role(tenant_id, user_id, role_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/users/{user_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_user_role(
    user_id: uuid.UUID, role_id: uuid.UUID, service: RbacServiceDep, tenant_id: TenantDep
) -> Response:
    await service.revoke_user_role(tenant_id, user_id, role_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/users/{user_id}/permissions/{code}", status_code=status.HTTP_204_NO_CONTENT
)
async def set_user_override(
    user_id: uuid.UUID,
    code: str,
    payload: SetOverrideRequest,
    service: RbacServiceDep,
    tenant_id: TenantDep,
) -> Response:
    await service.set_user_override(tenant_id, user_id, code, payload.effect)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/users/{user_id}/permissions/{code}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_user_override(
    user_id: uuid.UUID, code: str, service: RbacServiceDep, tenant_id: TenantDep
) -> Response:
    await service.remove_user_override(tenant_id, user_id, code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
