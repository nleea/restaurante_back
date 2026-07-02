"""Caso de uso: renovar tokens a partir de un refresh token válido (con rotación)."""

from __future__ import annotations

import uuid

from restaurante.modules.identity.application.dto import TokenPair
from restaurante.modules.identity.domain.ports import TokenService, UserRepository
from restaurante.shared.domain.errors import AuthenticationError, InvalidTokenError
from restaurante.shared.security.jwt import REFRESH


class RefreshTokenUseCase:
    def __init__(self, users: UserRepository, tokens: TokenService) -> None:
        self._users = users
        self._tokens = tokens

    async def execute(self, tenant_id: uuid.UUID, refresh_token: str) -> TokenPair:
        claims = self._tokens.decode(refresh_token)

        if claims.get("type") != REFRESH:
            raise InvalidTokenError("Se esperaba un refresh token.")
        if claims.get("tenant_id") != str(tenant_id):
            raise InvalidTokenError("El token no pertenece a este tenant.")

        try:
            user_id = uuid.UUID(str(claims.get("sub")))
        except (ValueError, TypeError) as exc:
            raise InvalidTokenError("Subject del token inválido.") from exc

        user = await self._users.get_by_id(tenant_id, user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("El usuario ya no está activo.")

        # Rotación: se emite también un nuevo refresh token.
        return TokenPair(
            access_token=self._tokens.create_access_token(user.id, tenant_id),
            refresh_token=self._tokens.create_refresh_token(user.id, tenant_id),
        )
