"""Raíz de composición del asistente.

Aquí se cumple lo que el diseño prometió: **la única forma de llegar al motor es el servicio
medido**. Este fichero construye `MeteredAssistant` y nada más; no expone el motor, ni el
adaptador de LangChain, ni un atajo "para pruebas". Si alguien necesita llamar al modelo,
tiene que pasar por la puerta que cobra.

El interruptor global y el límite por minuto entran desde los ajustes, no desde la base: son
nuestros, no del tenant.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.assistant.application.use_cases.conversation import (
    AssistantConversationService,
)
from restaurante.modules.assistant.application.use_cases.metering import MeteredAssistant
from restaurante.modules.assistant.application.use_cases.tools import (
    build_employee_registry,
)
from restaurante.modules.assistant.domain.ports import NullKnowledgeIndex, ToolSpec
from restaurante.modules.assistant.infrastructure.llm.engine import (
    LangChainConversationEngine,
)
from restaurante.modules.assistant.infrastructure.rate_limit import CacheRateLimiter
from restaurante.modules.assistant.infrastructure.repositories import (
    SqlAlchemyAssistantRepository,
)
from restaurante.modules.business.application.use_cases.manage_business import (
    BusinessService,
)
from restaurante.modules.business.infrastructure.repositories import (
    SqlAlchemyBusinessRepository,
)
from restaurante.modules.inventory.application.use_cases.manage_inventory import (
    InventoryService,
)
from restaurante.modules.inventory.infrastructure.repositories import (
    SqlAlchemyInventoryRepository,
)
from restaurante.modules.orders.infrastructure.api.deps import get_order_service
from restaurante.modules.reports.application.use_cases.reporting import ReportsService
from restaurante.modules.reports.infrastructure.repositories import (
    SqlAlchemyReportsRepository,
)
from restaurante.modules.storefront.infrastructure.api.deps import (
    get_storefront_service,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.cache import get_cache
from restaurante.shared.config import get_settings
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def build_metered(session: AsyncSession) -> MeteredAssistant:
    """El servicio medido. Es lo ÚNICO que este módulo deja construir."""
    settings = get_settings()
    return MeteredAssistant(
        SqlAlchemyAssistantRepository(session),
        LangChainConversationEngine(settings.assistant_api_key),
        # El índice sale inerte: no hay corpus, y el asistente está escrito para contestar
        # con herramientas cuando no devuelve nada.
        NullKnowledgeIndex(),
        CacheRateLimiter(get_cache()),
        kill_switch=settings.assistant_kill_switch,
        rate_limit_per_minute=settings.assistant_rate_limit_per_minute,
    )


def build_conversation_service(session: AsyncSession) -> AssistantConversationService:
    """El flujo, sin canal de cliente: esta vía es la del panel.

    El canal de WhatsApp lo enchufa quien recibe los mensajes entrantes, no una petición
    HTTP — igual que el escalado de alertas sólo existe en el worker.
    """
    return AssistantConversationService(
        build_metered(session),
        SqlAlchemyAssistantRepository(session),
        _NoChannel(),
        history_turns=get_settings().assistant_history_turns,
    )


async def employee_tools(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    permissions: set[str],
) -> list[ToolSpec]:
    """El registro del empleado, construido AHORA con sus permisos de AHORA.

    Se arma por petición a propósito: uno cacheado por sesión haría que quitarle un permiso a
    alguien tuviera efecto en su próximo login en vez de en su próxima pregunta.
    """
    return build_employee_registry(
        tenant_id=tenant_id,
        branch_id=branch_id,
        permissions=permissions,
        storefront=get_storefront_service(session),
        business=BusinessService(SqlAlchemyBusinessRepository(session)),
        orders=get_order_service(session),
        inventory=InventoryService(SqlAlchemyInventoryRepository(session)),
        reports=ReportsService(SqlAlchemyReportsRepository(session)),
    )


class _NoChannel:
    """Sin canal de cliente. El chat del panel contesta por HTTP, no por WhatsApp."""

    async def send(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
        contact_phone: str,
        text: str,
    ) -> bool:
        return False

    async def set_status(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID, status: str
    ) -> None:
        return None

    async def store_link(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> str:
        return ""

    async def last_outbound_text(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> str | None:
        return None


def get_metered(session: SessionDep) -> MeteredAssistant:
    return build_metered(session)


def get_conversation_service(session: SessionDep) -> AssistantConversationService:
    return build_conversation_service(session)


def get_repository(session: SessionDep) -> SqlAlchemyAssistantRepository:
    return SqlAlchemyAssistantRepository(session)


MeteredDep = Annotated[MeteredAssistant, Depends(get_metered)]
ConversationDep = Annotated[
    AssistantConversationService, Depends(get_conversation_service)
]
RepositoryDep = Annotated[SqlAlchemyAssistantRepository, Depends(get_repository)]
