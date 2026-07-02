"""Wiring de dependencias (composición de adaptadores) para la API de identidad."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.identity.application.use_cases.authorize import (
    AuthorizationService,
    CachedPermissionResolver,
)
from restaurante.modules.identity.application.use_cases.login import LoginUseCase
from restaurante.modules.identity.application.use_cases.manage_rbac import RbacService
from restaurante.modules.identity.application.use_cases.provision_user import (
    ProvisionUserUseCase,
)
from restaurante.modules.identity.application.use_cases.refresh import (
    RefreshTokenUseCase,
)
from restaurante.modules.identity.domain.entities import User
from restaurante.modules.identity.infrastructure.cache import RbacPermissionCache
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
    SqlAlchemyUserRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.audit.recorder import SqlAlchemyAuditRecorder
from restaurante.shared.cache import get_cache
from restaurante.shared.config import get_settings
from restaurante.shared.database import get_session
from restaurante.shared.domain.errors import AuthenticationError, InvalidTokenError
from restaurante.shared.security.jwt import ACCESS, JwtTokenService
from restaurante.shared.security.password import Argon2PasswordHasher

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


@lru_cache
def get_password_hasher() -> Argon2PasswordHasher:
    return Argon2PasswordHasher()


@lru_cache
def get_token_service() -> JwtTokenService:
    settings = get_settings()
    return JwtTokenService(
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        access_expire_minutes=settings.access_token_expire_minutes,
        refresh_expire_days=settings.refresh_token_expire_days,
    )


def get_user_repository(session: SessionDep) -> SqlAlchemyUserRepository:
    return SqlAlchemyUserRepository(session)


@lru_cache
def get_audit_recorder() -> SqlAlchemyAuditRecorder:
    # Usa su propia sesión por evento (ver SqlAlchemyAuditRecorder), por eso es
    # seguro cachearlo como singleton sin atarlo a la sesión del request.
    return SqlAlchemyAuditRecorder()


UserRepoDep = Annotated[SqlAlchemyUserRepository, Depends(get_user_repository)]
HasherDep = Annotated[Argon2PasswordHasher, Depends(get_password_hasher)]
TokensDep = Annotated[JwtTokenService, Depends(get_token_service)]
AuditDep = Annotated[SqlAlchemyAuditRecorder, Depends(get_audit_recorder)]


def get_login_use_case(
    users: UserRepoDep, hasher: HasherDep, tokens: TokensDep, audit: AuditDep
) -> LoginUseCase:
    return LoginUseCase(users=users, hasher=hasher, tokens=tokens, audit=audit)


def get_refresh_use_case(
    users: UserRepoDep, tokens: TokensDep
) -> RefreshTokenUseCase:
    return RefreshTokenUseCase(users=users, tokens=tokens)


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    tenant_id: TenantDep,
    users: UserRepoDep,
    tokens: TokensDep,
) -> User:
    """Resolves the authenticated user from the access token (Bearer)."""
    if not token:
        raise AuthenticationError("Falta el token de autenticación.")

    claims = tokens.decode(token)
    if claims.get("type") != ACCESS:
        raise InvalidTokenError("Se esperaba un access token.")
    if claims.get("tenant_id") != str(tenant_id):
        raise InvalidTokenError("El token no pertenece a este tenant.")

    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except (ValueError, TypeError) as exc:
        raise InvalidTokenError("Subject del token inválido.") from exc

    user = await users.get_by_id(tenant_id, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Usuario no encontrado o inactivo.")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


# --- RBAC wiring -----------------------------------------------------------
def get_rbac_repository(session: SessionDep) -> SqlAlchemyRbacRepository:
    return SqlAlchemyRbacRepository(session)


RbacRepoDep = Annotated[SqlAlchemyRbacRepository, Depends(get_rbac_repository)]


def get_permission_cache() -> RbacPermissionCache:
    settings = get_settings()
    return RbacPermissionCache(get_cache(), ttl_seconds=settings.cache_ttl_seconds)


PermissionCacheDep = Annotated[RbacPermissionCache, Depends(get_permission_cache)]


def get_authorization_service(
    rbac: RbacRepoDep, cache: PermissionCacheDep
) -> AuthorizationService:
    # Read-through cache in front of the DB resolver (see CachedPermissionResolver).
    return AuthorizationService(
        resolver=CachedPermissionResolver(inner=rbac, cache=cache)
    )


def get_rbac_service(rbac: RbacRepoDep, cache: PermissionCacheDep) -> RbacService:
    return RbacService(repo=rbac, cache=cache)


AuthorizationDep = Annotated[AuthorizationService, Depends(get_authorization_service)]
RbacServiceDep = Annotated[RbacService, Depends(get_rbac_service)]


def get_provision_user_use_case(
    users: UserRepoDep, hasher: HasherDep, rbac: RbacServiceDep
) -> ProvisionUserUseCase:
    return ProvisionUserUseCase(users=users, hasher=hasher, rbac=rbac)


ProvisionUserDep = Annotated[
    ProvisionUserUseCase, Depends(get_provision_user_use_case)
]


def require_permission(code: str) -> Callable[..., Awaitable[User]]:
    """Build a dependency that enforces the given permission code.

    Usage in a route: `Depends(require_permission("orders.create"))`. Returns the
    current user so the route can still receive it.
    """

    async def _checker(
        current_user: CurrentUserDep,
        tenant_id: TenantDep,
        authz: AuthorizationDep,
    ) -> User:
        await authz.ensure(tenant_id, current_user.id, code)
        return current_user

    return _checker
