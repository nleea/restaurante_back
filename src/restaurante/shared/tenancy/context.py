"""Contexto del tenant activo durante el ciclo de vida de un request.

Se usa un `ContextVar` para que el filtro automático de SQLAlchemy
(`shared.tenancy.filtering`) pueda conocer el tenant sin pasarlo explícitamente
por toda la cadena de llamadas.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token

from restaurante.shared.domain.errors import TenantNotResolvedError

_current_tenant_id: ContextVar[uuid.UUID | None] = ContextVar(
    "current_tenant_id", default=None
)


def set_current_tenant_id(tenant_id: uuid.UUID) -> Token[uuid.UUID | None]:
    """Fija el tenant del request actual. Devuelve un token para restaurarlo."""
    return _current_tenant_id.set(tenant_id)


def reset_current_tenant_id(token: Token[uuid.UUID | None]) -> None:
    """Restaura el valor anterior del ContextVar."""
    _current_tenant_id.reset(token)


def get_current_tenant_id() -> uuid.UUID | None:
    """Devuelve el tenant activo o ``None`` si no se resolvió."""
    return _current_tenant_id.get()


def require_current_tenant_id() -> uuid.UUID:
    """Devuelve el tenant activo o lanza si no hay ninguno resuelto."""
    tenant_id = _current_tenant_id.get()
    if tenant_id is None:
        raise TenantNotResolvedError("No hay tenant resuelto en el contexto actual.")
    return tenant_id
