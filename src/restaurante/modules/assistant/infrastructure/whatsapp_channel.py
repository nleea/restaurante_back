"""El adaptador hacia messaging. Único fichero del asistente que conoce WhatsApp.

Misma postura que el escalado de alertas: la flecha SALE. El dominio y la aplicación del
asistente no importan messaging; la raíz de composición enchufa esto, y si no lo enchufa el
asistente sigue funcionando — sin vía de cliente, con el chat de administración intacto.

Se escribe por el gateway GUARDADO, que rechaza escribir a quien no escribió primero. Aquí
esa propiedad no cuesta nada: el asistente sólo contesta a alguien que acaba de escribir.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.messaging.application.use_cases.autoreply import (
    AutoreplyService,
)
from restaurante.modules.messaging.domain.ports import WhatsAppGateway
from restaurante.modules.messaging.infrastructure.repositories import (
    SqlAlchemyMessagingRepository,
)

logger = logging.getLogger(__name__)


class WhatsAppConversationChannel:
    """`ConversationChannel` sobre el canal de WhatsApp ya existente."""

    def __init__(
        self,
        session: AsyncSession,
        autoreply: AutoreplyService,
        gateway: WhatsAppGateway,
    ) -> None:
        self._repo = SqlAlchemyMessagingRepository(session)
        # El servicio de autoreply se usa SÓLO para el enlace con token: es quien decide si
        # se reutiliza el token vivo o se acuña otro, y duplicar esa decisión aquí sería
        # tener dos reglas para la vida de un mismo token.
        self._autoreply = autoreply
        self._gateway = gateway

    async def send(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
        contact_phone: str,
        text: str,
    ) -> bool:
        session = await self._repo.get_session_for_branch(tenant_id, branch_id)
        if session is None:
            logger.warning(
                "Respuesta del asistente no enviada: la sucursal %s no tiene número",
                branch_id,
            )
            return False
        try:
            await self._gateway.send_text(session, contact_phone, text)
        except Exception:  # noqa: BLE001 - un envío fallido no puede tumbar el turno
            logger.warning("No se pudo enviar la respuesta del asistente", exc_info=True)
            return False
        # Se persiste como mensaje del sistema: un agente que abra el inbox tiene que ver lo
        # que el asistente contestó. Sin esto, tomaría la conversación a ciegas.
        await self._repo.add_message(
            tenant_id,
            branch_id,
            conversation_id,
            sender_type="system",
            content=text,
        )
        return True

    async def set_status(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID, status: str
    ) -> None:
        await self._repo.update_conversation_status(tenant_id, conversation_id, status)

    async def last_outbound_text(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> str | None:
        return await self._repo.last_outbound_content(tenant_id, conversation_id)

    async def store_link(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> str:
        """El enlace de la carta para esta conversación.

        Reutiliza el token vivo si lo hay (lo decide `mint_store_link`): un enlace nuevo por
        cada mensaje llenaría el hilo de URLs distintas para el mismo carrito.
        """
        conversation = await self._repo.get_conversation(tenant_id, conversation_id)
        if conversation is None:
            return ""
        return await self._autoreply.mint_store_link(conversation)
