"""Middleware ASGI que resuelve el tenant a partir del subdominio.

Se implementa como middleware ASGI puro (no `BaseHTTPMiddleware`) para que el
`ContextVar` del tenant se fije en la MISMA tarea que ejecuta el endpoint y el
filtro automático de SQLAlchemy lo vea de forma fiable.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.context import (
    reset_current_tenant_id,
    set_current_tenant_id,
)
from restaurante.shared.tenancy.models import TenantModel

# Rutas que no requieren tenant (documentación, salud, etc.)
DEFAULT_EXEMPT_PATHS: frozenset[str] = frozenset(
    {"/health", "/docs", "/redoc", "/openapi.json"}
)


def _extract_subdomain(host: str, base_domain: str) -> str | None:
    """Extrae el slug del tenant de un host ``<slug>.<base_domain>``."""
    host = host.split(":", 1)[0].lower().strip()
    base = base_domain.lower().strip()
    suffix = f".{base}"
    if not host.endswith(suffix):
        return None
    sub = host[: -len(suffix)]
    # Sólo un nivel de subdominio y no vacío.
    if not sub or "." in sub:
        return None
    return sub


class TenantResolverMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        base_domain: str,
        exempt_paths: Iterable[str] = DEFAULT_EXEMPT_PATHS,
    ) -> None:
        self.app = app
        self.base_domain = base_domain
        self.exempt_paths = frozenset(exempt_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if path in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        host = request.headers.get("host", "")
        slug = _extract_subdomain(host, self.base_domain)

        if slug is None:
            await self._reject(
                scope, receive, send, "Subdominio de tenant requerido."
            )
            return

        async with SessionFactory() as session:
            result = await session.execute(
                select(TenantModel).where(
                    TenantModel.slug == slug, TenantModel.is_active.is_(True)
                )
            )
            tenant = result.scalar_one_or_none()

        if tenant is None:
            await self._reject(
                scope, receive, send, f"Tenant '{slug}' no existe o está inactivo."
            )
            return

        token = set_current_tenant_id(tenant.id)
        scope.setdefault("state", {})["tenant_id"] = tenant.id
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_tenant_id(token)

    @staticmethod
    async def _reject(
        scope: Scope, receive: Receive, send: Send, detail: str
    ) -> None:
        response = JSONResponse(
            status_code=404, content={"code": "tenant_not_resolved", "detail": detail}
        )
        await response(scope, receive, send)
