"""Punto de entrada: fábrica de la aplicación FastAPI."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Registra TODOS los modelos ORM en Base.metadata para que las claves foráneas
# entre módulos (p.ej. tenants.city_id -> cities) se resuelvan al configurar los
# mappers. Sin esto, la primera consulta a un modelo con FK cruzada falla con
# NoReferencedTableError.
import restaurante.shared.models_registry  # noqa: F401
from restaurante.modules.audit.infrastructure.api.router import (
    router as audit_router,
)
from restaurante.modules.cash.infrastructure.api.router import router as cash_router
from restaurante.modules.catalog.infrastructure.api.router import (
    router as catalog_router,
)
from restaurante.modules.customers.infrastructure.api.router import (
    router as customers_router,
)
from restaurante.modules.delivery.infrastructure.api.router import (
    router as delivery_router,
)
from restaurante.modules.finance.infrastructure.api.router import (
    router as finance_router,
)
from restaurante.modules.identity.infrastructure.api.branches_router import (
    router as branches_router,
)
from restaurante.modules.identity.infrastructure.api.rbac_router import (
    router as rbac_router,
)
from restaurante.modules.identity.infrastructure.api.router import router as auth_router
from restaurante.modules.inventory.infrastructure.api.router import (
    router as inventory_router,
)
from restaurante.modules.kitchen.infrastructure.api.router import (
    router as kitchen_router,
)
from restaurante.modules.menu.infrastructure.api.router import router as menu_router
from restaurante.modules.orders.infrastructure.api.router import (
    router as orders_router,
)
from restaurante.modules.purchasing.infrastructure.api.router import (
    router as purchasing_router,
)
from restaurante.modules.recipes.infrastructure.api.router import (
    router as recipes_router,
)
from restaurante.modules.staff.infrastructure.api.router import router as staff_router
from restaurante.shared.api.errors import register_exception_handlers
from restaurante.shared.config import get_settings
from restaurante.shared.tenancy.filtering import install_tenant_filter
from restaurante.shared.tenancy.middleware import TenantResolverMiddleware


def create_app() -> FastAPI:
    settings = get_settings()

    # Activa el filtro automático de tenancy a nivel de sesión SQLAlchemy.
    install_tenant_filter()

    app = FastAPI(title=settings.app_name, debug=settings.debug)

    # Middleware de resolución de tenant por subdominio (ASGI puro).
    app.add_middleware(TenantResolverMiddleware, base_domain=settings.base_domain)

    # CORS: se añade DESPUÉS del resolver de tenant para que quede en la capa más externa
    # (Starlette ejecuta el último middleware añadido primero). Así el preflight OPTIONS del
    # navegador se responde con las cabeceras CORS antes de tocar la lógica de tenant.
    # Usamos Authorization (Bearer), no cookies, pero permitimos credenciales por si se usan.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    @app.get("/health", tags=["infra"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(branches_router)
    app.include_router(rbac_router)
    app.include_router(menu_router)
    app.include_router(staff_router)
    app.include_router(inventory_router)
    app.include_router(recipes_router)
    app.include_router(orders_router)
    app.include_router(cash_router)
    app.include_router(kitchen_router)
    app.include_router(delivery_router)
    app.include_router(purchasing_router)
    app.include_router(customers_router)
    app.include_router(finance_router)
    app.include_router(catalog_router)
    app.include_router(audit_router)

    return app


app = create_app()
