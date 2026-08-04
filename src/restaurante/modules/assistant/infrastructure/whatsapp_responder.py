"""Quien contesta cuando el mensaje entrante es para el asistente.

Implementa el `AssistantResponder` que messaging declara como puerto LOCAL, así que messaging
sigue sin conocer este módulo: recibe un objeto con un método y no sabe qué hay detrás. Sin
este adaptador enchufado, ninguna conversación entra en modo bot y todas las atiende una
persona — exactamente como antes de la fase 4.

Aquí se arma el registro del CLIENTE, que es el que no contiene ventas ni stock. Que se
construya en este fichero y no dentro del servicio no es casual: el registro depende del
llamador, y el llamador es lo único que este adaptador sabe con certeza.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.assistant.application.use_cases.conversation import (
    AssistantConversationService,
    InboundContext,
)
from restaurante.modules.assistant.application.use_cases.tools import (
    build_customer_registry,
)
from restaurante.modules.assistant.infrastructure.api.deps import build_metered
from restaurante.modules.assistant.infrastructure.business_hours import (
    BusinessOpeningHours,
)
from restaurante.modules.assistant.infrastructure.repositories import (
    SqlAlchemyAssistantRepository,
)
from restaurante.modules.assistant.infrastructure.whatsapp_channel import (
    WhatsAppConversationChannel,
)
from restaurante.modules.business.application.use_cases.manage_business import (
    BusinessService,
)
from restaurante.modules.business.infrastructure.repositories import (
    SqlAlchemyBusinessRepository,
)
from restaurante.modules.messaging.application.use_cases.autoreply import (
    AutoreplyService,
)
from restaurante.modules.messaging.domain.entities import WhatsAppConversation
from restaurante.modules.messaging.domain.ports import WhatsAppGateway
from restaurante.modules.messaging.infrastructure.repositories import (
    SqlAlchemyMessagingRepository,
)
from restaurante.modules.orders.infrastructure.api.deps import get_order_service
from restaurante.modules.storefront.infrastructure.api.deps import (
    get_storefront_service,
)
from restaurante.shared.config import get_settings
from restaurante.shared.links import order_edit_url

logger = logging.getLogger(__name__)


class WhatsAppAssistantResponder:
    def __init__(
        self,
        session: AsyncSession,
        autoreply: AutoreplyService,
        gateway: WhatsAppGateway,
    ) -> None:
        self._session = session
        self._autoreply = autoreply
        self._gateway = gateway

    async def respond(
        self,
        conversation: WhatsAppConversation,
        contact_id: uuid.UUID,
        contact_phone: str,
        text: str,
    ) -> bool:
        settings = get_settings()
        business = BusinessService(SqlAlchemyBusinessRepository(self._session))
        service = AssistantConversationService(
            build_metered(self._session),
            SqlAlchemyAssistantRepository(self._session),
            WhatsAppConversationChannel(self._session, self._autoreply, self._gateway),
            business_name=await self._business_name(business, conversation.tenant_id),
            history_turns=settings.assistant_history_turns,
            # El horario apaga al asistente, no a la vista de "mi pedido".
            hours=BusinessOpeningHours(business),
        )
        slug = await SqlAlchemyMessagingRepository(self._session).tenant_slug(
            conversation.tenant_id
        )
        tools = build_customer_registry(
            tenant_id=conversation.tenant_id,
            branch_id=conversation.branch_id,
            storefront=get_storefront_service(self._session),
            business=business,
            orders=get_order_service(self._session),
            # Sin esto no hay herramienta de "mis pedidos": preguntar por un pedido exige
            # saber de quién es, y lo único que sabemos con certeza es desde qué contacto
            # escribió.
            whatsapp_contact_id=contact_id,
            # El enlace se compone aquí, donde se sabe el subdominio del negocio. La
            # herramienta sólo pone el token: es de sólo lectura, y componer una URL no la
            # convierte en otra cosa.
            order_edit_link=lambda token: order_edit_url(
                settings.storefront_base_url, slug, token
            ),
        )
        return await service.handle_inbound(
            InboundContext(
                tenant_id=conversation.tenant_id,
                branch_id=conversation.branch_id,
                conversation_id=conversation.id,
                contact_id=contact_id,
                contact_phone=contact_phone,
                status=conversation.status,
                text=text,
            ),
            tools,
        )

    async def _business_name(
        self, business: BusinessService, tenant_id: uuid.UUID
    ) -> str:
        """Cómo se presenta el negocio. El del PERFIL, nunca el de la sucursal.

        Es la misma piedra que ya tropezó el saludo de la fase 2: la sucursal se llama "Main
        Branch" hasta que alguien la renombra, y un asistente diciendo "soy de Main Branch"
        es lo que hace que un restaurante lo apague.
        """
        try:
            profile = await business.get_profile(tenant_id)
        except Exception:  # noqa: BLE001 - un nombre no puede costar la respuesta
            logger.warning("No se pudo leer el perfil del negocio", exc_info=True)
            return "el restaurante"
        return profile.name or "el restaurante"
