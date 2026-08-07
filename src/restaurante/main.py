"""Punto de entrada: fábrica de la aplicación FastAPI."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Registra TODOS los modelos ORM en Base.metadata para que las claves foráneas
# entre módulos (p.ej. tenants.city_id -> cities) se resuelvan al configurar los
# mappers. Sin esto, la primera consulta a un modelo con FK cruzada falla con
# NoReferencedTableError.
import restaurante.shared.models_registry  # noqa: F401
from restaurante.modules.alerts.infrastructure.api.router import (
    router as alerts_router,
)
from restaurante.modules.assistant.infrastructure.api.router import (
    router as assistant_router,
)
from restaurante.modules.audit.infrastructure.api.router import (
    router as audit_router,
)
from restaurante.modules.business.infrastructure.api.router import (
    router as business_router,
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
from restaurante.modules.guest_profile.infrastructure.api.router import (
    router as guest_profile_router,
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
from restaurante.modules.media.infrastructure.api.router import router as media_router
from restaurante.modules.menu.infrastructure.api.router import router as menu_router
from restaurante.modules.messaging.infrastructure.api.router import (
    router as messaging_router,
)
from restaurante.modules.messaging.infrastructure.api.router import (
    webhook_router as messaging_webhook_router,
)
from restaurante.modules.orders.infrastructure.api.router import (
    refunds_router,
)
from restaurante.modules.orders.infrastructure.api.router import (
    router as orders_router,
)
from restaurante.modules.purchasing.infrastructure.api.router import (
    router as purchasing_router,
)
from restaurante.modules.recipes.infrastructure.api.router import (
    router as recipes_router,
)
from restaurante.modules.reports.infrastructure.api.router import (
    router as reports_router,
)
from restaurante.modules.staff.infrastructure.api.router import router as staff_router
from restaurante.modules.storefront.infrastructure.api.order_edit_router import (
    router as storefront_order_edit_router,
)
from restaurante.modules.storefront.infrastructure.api.router import (
    router as storefront_router,
)
from restaurante.shared.api.errors import register_exception_handlers
from restaurante.shared.api.prefix import API_PREFIX, api_path
from restaurante.shared.config import get_settings
from restaurante.shared.tenancy.filtering import install_tenant_filter
from restaurante.shared.tenancy.middleware import TenantResolverMiddleware


def create_app() -> FastAPI:
    settings = get_settings()

    # Activa el filtro automático de tenancy a nivel de sesión SQLAlchemy.
    install_tenant_filter()

    # La documentación se mueve con la API: detrás del túnel sólo `/api/*` llega aquí, así
    # que un `/docs` en la raíz sería servido por el front y respondería con el SPA.
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        docs_url=api_path("/docs"),
        redoc_url=api_path("/redoc"),
        openapi_url=api_path("/openapi.json"),
        swagger_ui_oauth2_redirect_url=api_path("/docs/oauth2-redirect"),
    )

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

    # TODA la API cuelga de `/api`. Un único router agregador y no un prefijo repetido en
    # cada `include_router`: así "dónde vive la API" es una línea, y no veinticuatro que
    # alguien puede olvidar al añadir un módulo.
    #
    # El prefijo existe porque el front del tenant y su API comparten hostname (el tenant se
    # resuelve por el subdominio), y catorce rutas del SPA se llaman igual que catorce
    # prefijos de la API. Ver `shared/api/prefix.py`.
    api = APIRouter(prefix=API_PREFIX)

    @api.get("/health", tags=["infra"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    api.include_router(auth_router)
    api.include_router(branches_router)
    api.include_router(rbac_router)
    api.include_router(menu_router)
    api.include_router(staff_router)
    api.include_router(inventory_router)
    api.include_router(recipes_router)
    api.include_router(orders_router)
    api.include_router(refunds_router)
    api.include_router(cash_router)
    api.include_router(kitchen_router)
    api.include_router(delivery_router)
    api.include_router(purchasing_router)
    api.include_router(customers_router)
    api.include_router(finance_router)
    api.include_router(catalog_router)
    api.include_router(audit_router)
    api.include_router(reports_router)
    # ANTES del storefront: `/storefront/orders/{token}` y `/storefront/{branch_code}/menu`
    # tienen la misma forma, y gana la que se declaró primero.
    api.include_router(storefront_order_edit_router)
    api.include_router(storefront_router)
    api.include_router(guest_profile_router)
    api.include_router(business_router)
    api.include_router(media_router)
    api.include_router(messaging_router)
    api.include_router(alerts_router)
    api.include_router(assistant_router)
    # Authenticated by a shared secret, not by a user — the bridge has no session.
    api.include_router(messaging_webhook_router)

    app.include_router(api)
    return app


app = create_app()
