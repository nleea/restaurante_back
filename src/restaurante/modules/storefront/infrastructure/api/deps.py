"""Dependency wiring for the public Storefront API.

Composes the storefront service from the SAME request session as the reused staff
services (orders, delivery) so a whole order intake shares one unit of work. The public
surface depends ONLY on ``TenantDep`` (tenant by subdomain) — no ``require_permission``.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Protocol

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.business.application.use_cases.manage_business import (
    BusinessService,
)
from restaurante.modules.business.infrastructure.repositories import (
    SqlAlchemyBusinessRepository,
)
from restaurante.modules.customers.application.use_cases.manage_customers import (
    CustomerService,
)
from restaurante.modules.customers.infrastructure.repositories import (
    SqlAlchemyCustomersRepository,
)
from restaurante.modules.delivery.infrastructure.api.deps import get_delivery_service
from restaurante.modules.delivery.infrastructure.readiness import (
    SqlAlchemyDeliveryReadiness,
)
from restaurante.modules.kitchen.application.use_cases.manage_kitchen import (
    KitchenService,
)
from restaurante.modules.kitchen.infrastructure.repositories import (
    SqlAlchemyKitchenRepository,
)
from restaurante.modules.menu.application.use_cases.manage_appearance import (
    AppearanceService,
)
from restaurante.modules.menu.infrastructure.repositories import (
    SqlAlchemyMenuRepository,
)
from restaurante.modules.messaging.infrastructure.api.deps import (
    build_customer_channel,
)
from restaurante.modules.orders.application.use_cases.manage_payments import (
    PaymentService,
)
from restaurante.modules.orders.infrastructure.api.deps import (
    build_orders_readiness,
    get_order_service,
    get_payment_service,
)
from restaurante.modules.orders.infrastructure.payment_proof import (
    store_payment_proof,
)
from restaurante.modules.storefront.application.use_cases.edit_order import (
    OrderEditService,
)
from restaurante.modules.storefront.application.use_cases.manage_storefront import (
    StorefrontService,
)
from restaurante.modules.storefront.infrastructure.order_edit_reader import (
    SqlAlchemyOrderEditReader,
)
from restaurante.modules.storefront.infrastructure.repositories import (
    SqlAlchemyStorefrontRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.audit.recorder import SqlAlchemyAuditRecorder
from restaurante.shared.database import get_session
from restaurante.shared.storage.deps import build_object_storage
from restaurante.shared.storage.ports import StorageGateway

storage_dep = Annotated[StorageGateway, Depends(build_object_storage)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_appearance_service(session: SessionDep) -> AppearanceService:
    return AppearanceService(repo=SqlAlchemyMenuRepository(session))


AppearanceServiceDep = Annotated[AppearanceService, Depends(get_appearance_service)]


def get_storefront_service(session: SessionDep) -> StorefrontService:
    # Un solo canal para las dos cosas que el storefront le pide: resolver el token del
    # enlace y avisar "recibimos tu pedido".
    channel = build_customer_channel(session)
    return StorefrontService(
        repo=SqlAlchemyStorefrontRepository(session),
        order_service=get_order_service(session),
        customer_service=CustomerService(repo=SqlAlchemyCustomersRepository(session)),
        delivery_service=get_delivery_service(session),
        channel_directory=channel,
        customer_notifier=channel,
        # Una sede sin pin o sin bandas no puede ponerle precio a un domicilio. Decírselo al
        # cliente en el checkout es peor noticia dada honestamente; aceptarlo lo deja esperando
        # un enlace de pago que nadie va a poder emitir.
        delivery_readiness=SqlAlchemyDeliveryReadiness(session),
    )


StorefrontServiceDep = Annotated[StorefrontService, Depends(get_storefront_service)]


class _KitchenDispatchAdapter:
    """Adapta la cocina al puerto `KitchenDispatch` del storefront.

    Vive en el composition root para que la aplicación del storefront no importe cocina.
    Deliberadamente SIN la puerta de pago (`orders_payment`), igual que la ruta que usa
    `get_order_service`: por aquí sólo se enruta un pedido que YA está en cocina, así que la
    puerta ya se cruzó una vez. Volver a preguntarla sólo podría dar un falso "no" — y un
    falso "no" aquí deja unas papas facturadas que nadie cocina, que es el fallo que este
    adaptador existe para evitar.
    """

    def __init__(self, kitchen: KitchenService) -> None:
        self._kitchen = kitchen

    async def route_order(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> None:
        await self._kitchen.route_order(tenant_id, order_id)


def get_order_edit_service(session: SessionDep) -> OrderEditService:
    # Misma sesión para todo: leer el pedido, escribirlo y enrutarlo a cocina son un solo
    # gesto del cliente, y lo añadido tiene que ser visible cuando se enrute.
    return OrderEditService(
        repo=SqlAlchemyStorefrontRepository(session),
        orders=get_order_service(session),
        reader=SqlAlchemyOrderEditReader(session),
        kitchen=_KitchenDispatchAdapter(
            KitchenService(
                repo=SqlAlchemyKitchenRepository(session),
                orders_readiness=build_orders_readiness(session),
            )
        ),
        # Su propia sesión por evento (ver `SqlAlchemyAuditRecorder`): el rastro de quién
        # cambió el pedido no debe irse con un rollback del pedido.
        audit=SqlAlchemyAuditRecorder(),
    )


OrderEditServiceDep = Annotated[OrderEditService, Depends(get_order_edit_service)]


def get_business_service(session: SessionDep) -> BusinessService:
    return BusinessService(repo=SqlAlchemyBusinessRepository(session))


BusinessServiceDep = Annotated[BusinessService, Depends(get_business_service)]


# El servicio de pagos, para que el cliente pueda DECLARAR (nunca cobrar) desde el enlace. Se
# reusa el mismo que usa el personal: la regla de que una declaración no es un pago vive dentro,
# y tenerla en un sitio es lo que hace que no se pueda saltar desde aquí.
PaymentServiceDep = Annotated[PaymentService, Depends(get_payment_service)]


class ProofStore(Protocol):
    """Guardar el comprobante y devolver su URL pública.

    Es una dependencia y no una llamada directa para que la ruta no conozca R2 — y para que una
    prueba pueda sustituirla sin tocar la red. Lo que se prueba de este endpoint es la regla
    (el saldo no se mueve), no que Cloudflare responda.
    """

    async def __call__(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        content_type: str,
        data: bytes,
    ) -> str: ...


def get_proof_store(
    storage: storage_dep,
) -> ProofStore:
    async def store(
        tenant_id: uuid.UUID, order_id: uuid.UUID, content_type: str, data: bytes
    ) -> str:
        return await store_payment_proof(
            tenant_id, order_id, content_type, data, storage=storage
        )

    return store


ProofStoreDep = Annotated[ProofStore, Depends(get_proof_store)]
