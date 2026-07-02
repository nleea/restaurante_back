"""Adaptador de tokens JWT (access + refresh). Implementa el puerto TokenService."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from restaurante.shared.domain.errors import InvalidTokenError

ACCESS = "access"
REFRESH = "refresh"


class JwtTokenService:
    def __init__(
        self,
        secret: str,
        algorithm: str,
        access_expire_minutes: int,
        refresh_expire_days: int,
    ) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._access_expire = timedelta(minutes=access_expire_minutes)
        self._refresh_expire = timedelta(days=refresh_expire_days)

    def _create(
        self,
        subject: uuid.UUID,
        tenant_id: uuid.UUID,
        token_type: str,
        expires_delta: timedelta,
    ) -> str:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": str(subject),
            "tenant_id": str(tenant_id),
            "type": token_type,
            "iat": now,
            "exp": now + expires_delta,
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def create_access_token(self, subject: uuid.UUID, tenant_id: uuid.UUID) -> str:
        return self._create(subject, tenant_id, ACCESS, self._access_expire)

    def create_refresh_token(self, subject: uuid.UUID, tenant_id: uuid.UUID) -> str:
        return self._create(subject, tenant_id, REFRESH, self._refresh_expire)

    def decode(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("Token inválido o expirado.") from exc
