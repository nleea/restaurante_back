"""The outbound invariant: we only ever reply, never initiate.

This is the single rule that protects the number from being banned, so it is a
decorator around the port rather than a check each caller remembers to perform.
Change 2 (auto-reply) and change 4 (assistant) will both send messages through this
same gateway; neither can bypass the rule by forgetting it, because the composition
root only ever builds the guarded instance (`build_whatsapp_gateway`).

Rejected alternative: checking inside `MessagingService.send_reply`. Later modules
send without going through that service, and an invariant that depends on
discipline is not an invariant.
"""

from __future__ import annotations

import logging

from restaurante.modules.messaging.domain.entities import WhatsAppSession
from restaurante.modules.messaging.domain.errors import ContactNotReachableError
from restaurante.modules.messaging.domain.ports import (
    MessagingRepository,
    WhatsAppGateway,
)

logger = logging.getLogger(__name__)


class GuardedWhatsAppGateway:
    """Implements `WhatsAppGateway`, delegating only to reachable contacts."""

    def __init__(
        self, inner: WhatsAppGateway, repository: MessagingRepository
    ) -> None:
        self._inner = inner
        self._repository = repository

    async def send_text(
        self, session: WhatsAppSession, to_phone: str, body: str
    ) -> str:
        reachable = await self._repository.is_reachable(session.tenant_id, to_phone)
        if not reachable:
            # Logged at warning: a refusal here means some caller tried to initiate,
            # which is a bug worth seeing rather than a routine outcome.
            logger.warning(
                "Refused unsolicited WhatsApp send to a phone with no inbound message "
                "(tenant=%s, branch=%s)",
                session.tenant_id,
                session.branch_id,
            )
            raise ContactNotReachableError(
                "No se puede escribir a un número que nunca nos ha escrito."
            )
        return await self._inner.send_text(session, to_phone, body)

    async def send_media(
        self,
        session: WhatsAppSession,
        to_phone: str,
        data: bytes,
        *,
        mimetype: str,
        filename: str,
        caption: str = "",
    ) -> str:
        """Misma comprobación que `send_text`, y por el mismo motivo.

        Al contrario que `fetch_media` —que sólo lee—, esto ESCRIBE a un teléfono. Un archivo no
        solicitado es tan capaz de hacer que baneen el número como un texto no solicitado; más,
        si acaso.
        """
        reachable = await self._repository.is_reachable(session.tenant_id, to_phone)
        if not reachable:
            logger.warning(
                "Refused unsolicited WhatsApp media to a phone with no inbound message "
                "(tenant=%s, branch=%s)",
                session.tenant_id,
                session.branch_id,
            )
            raise ContactNotReachableError(
                "No se puede escribir a un número que nunca nos ha escrito."
            )
        return await self._inner.send_media(
            session, to_phone, data, mimetype=mimetype, filename=filename, caption=caption
        )

    async def fetch_media(
        self,
        session: WhatsAppSession,
        provider_message_id: str,
        remote_jid: str,
        *,
        from_me: bool = False,
    ) -> bytes:
        """Passthrough, y **a propósito sin comprobar nada**.

        La invariante que este decorador protege es de SALIDA: no escribirle a quien no nos
        escribió. Bajar el archivo de un mensaje que YA nos mandaron no le escribe a nadie,
        así que aquí no hay nada que guardar. Queda dicho porque un `fetch` sin comprobación
        dentro del guard parece un olvido, y el siguiente que pase va a querer "arreglarlo".
        """
        return await self._inner.fetch_media(
            session, provider_message_id, remote_jid, from_me=from_me
        )

    async def start_pairing(
        self, session: WhatsAppSession, webhook_url: str, webhook_secret: str
    ) -> str | None:
        """Passthrough: emparejar no envía nada a nadie, así que no hay nada que guardar."""
        return await self._inner.start_pairing(session, webhook_url, webhook_secret)
