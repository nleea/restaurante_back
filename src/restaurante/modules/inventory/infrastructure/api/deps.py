"""Dependency wiring for the Inventory API.

Aquí se enchufa el anunciante de alertas. Es el ÚNICO punto en el que inventario roza el
módulo de alertas, y lo hace contra un protocolo: el servicio no sabe qué hay al otro lado, y
sin Redis se le pasa el anunciante nulo — el stock bajo lo sigue encontrando el barrido.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.alerts.infrastructure.alert_queue import (
    ArqAlertQueue,
    NullAlertQueue,
)
from restaurante.modules.inventory.application.use_cases.manage_inventory import (
    InventoryService,
    StockAlertAnnouncer,
)
from restaurante.modules.inventory.infrastructure.repositories import (
    SqlAlchemyInventoryRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.config import get_settings
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


@lru_cache
def get_alert_announcer() -> StockAlertAnnouncer:
    """Uno por proceso: sostiene un pool, así que tiene que sobrevivir a la petición.

    Sin Redis, el nulo. No es una degradación silenciosa: es el diseño — la latencia es
    opcional, la garantía la da el barrido del worker.
    """
    if get_settings().cache_backend != "redis":
        return NullAlertQueue()
    return ArqAlertQueue(get_settings().redis_url)


def get_inventory_service(session: SessionDep) -> InventoryService:
    return InventoryService(
        repo=SqlAlchemyInventoryRepository(session), alerts=get_alert_announcer()
    )


InventoryServiceDep = Annotated[InventoryService, Depends(get_inventory_service)]
