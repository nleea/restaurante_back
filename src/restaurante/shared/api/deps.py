"""Dependencias FastAPI transversales."""

from __future__ import annotations

import uuid

from fastapi import Request

from restaurante.shared.domain.errors import TenantNotResolvedError


def get_tenant_id(request: Request) -> uuid.UUID:
    """Devuelve el tenant resuelto por el middleware para este request."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not isinstance(tenant_id, uuid.UUID):
        raise TenantNotResolvedError("No hay tenant resuelto para este request.")
    return tenant_id
