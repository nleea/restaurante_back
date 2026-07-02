"""Endpoints de autenticación."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from restaurante.modules.identity.application.use_cases.login import LoginUseCase
from restaurante.modules.identity.application.use_cases.refresh import (
    RefreshTokenUseCase,
)
from restaurante.modules.identity.domain.entities import User
from restaurante.modules.identity.infrastructure.api.deps import (
    AuthorizationDep,
    TenantDep,
    get_current_user,
    get_login_use_case,
    get_refresh_use_case,
)
from restaurante.modules.identity.infrastructure.api.schemas import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    payload: LoginRequest,
    tenant_id: TenantDep,
    use_case: Annotated[LoginUseCase, Depends(get_login_use_case)],
) -> TokenResponse:
    client_ip = request.client.host if request.client else None
    tokens = await use_case.execute(
        tenant_id=tenant_id,
        email=payload.email,
        password=payload.password,
        ip=client_ip,
    )
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    tenant_id: TenantDep,
    use_case: Annotated[RefreshTokenUseCase, Depends(get_refresh_use_case)],
) -> TokenResponse:
    tokens = await use_case.execute(
        tenant_id=tenant_id, refresh_token=payload.refresh_token
    )
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
    )


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: TenantDep,
    authz: AuthorizationDep,
) -> UserResponse:
    permissions = await authz.effective_codes(tenant_id, current_user.id)
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        permissions=sorted(permissions),
    )
