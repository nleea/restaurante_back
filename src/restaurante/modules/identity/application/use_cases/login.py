"""Caso de uso: autenticar un usuario y emitir el par de tokens."""

from __future__ import annotations

import uuid

from restaurante.modules.identity.application.dto import TokenPair
from restaurante.modules.identity.domain.ports import (
    PasswordHasher,
    TokenService,
    UserRepository,
)
from restaurante.modules.identity.domain.value_objects import Email
from restaurante.shared.domain.audit import AuditEvent, AuditEventRecorder
from restaurante.shared.domain.errors import AuthenticationError

LOGIN_SUCCESS = "login.success"
LOGIN_FAILURE = "login.failure"


class LoginUseCase:
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        tokens: TokenService,
        audit: AuditEventRecorder | None = None,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens
        self._audit = audit

    async def execute(
        self,
        tenant_id: uuid.UUID,
        email: str,
        password: str,
        ip: str | None = None,
    ) -> TokenPair:
        normalized_email = Email.normalize(email)
        user = await self._users.get_by_email(tenant_id, normalized_email)

        # Mensaje genérico y verificación incondicional para no filtrar si el
        # email existe (mitiga enumeración de usuarios y timing). La auditoría se
        # registra DESPUÉS de tomada la decisión, de forma uniforme en ambas ramas,
        # por lo que no introduce un canal de tiempo dependiente del email.
        if user is None or not user.is_active or not self._hasher.verify(
            password, user.hashed_password
        ):
            await self._record(
                tenant_id,
                LOGIN_FAILURE,
                actor_id=user.id if user is not None else None,
                ip=ip,
                detail=f"email={normalized_email}",
            )
            raise AuthenticationError("Credenciales inválidas.")

        await self._record(tenant_id, LOGIN_SUCCESS, actor_id=user.id, ip=ip)

        return TokenPair(
            access_token=self._tokens.create_access_token(user.id, tenant_id),
            refresh_token=self._tokens.create_refresh_token(user.id, tenant_id),
        )

    async def _record(
        self,
        tenant_id: uuid.UUID,
        action: str,
        *,
        actor_id: uuid.UUID | None = None,
        ip: str | None = None,
        detail: str | None = None,
    ) -> None:
        if self._audit is None:
            return
        await self._audit.record(
            AuditEvent(
                tenant_id=tenant_id,
                action=action,
                actor_id=actor_id,
                entity_type="user",
                entity_id=actor_id,
                ip=ip,
                detail=detail,
            )
        )
