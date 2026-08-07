"""Messaging use cases: the inbound webhook, the shared inbox, and sessions.

Three rules live here rather than in the adapters:

- **Conversation continuity is an idle window.** An inbound message joins the
  contact's open thread on that branch; past `idle_hours` of silence the old thread is
  closed and a new one opened. No sweeper job — the check happens where it matters.
- **Outbound is persisted before it is transmitted.** A reply is written `pending`,
  handed to the gateway, then marked `sent` or `failed`. A message swallowed by a dead
  bridge must still be visible, or the agent believes it landed.
- **The doorbell is best-effort and rings after the write.** The message is committed
  first; a broker outage degrades the inbox to polling and loses nothing.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from restaurante.modules.messaging.application.use_cases.autoreply import (
    AutoreplyService,
)
from restaurante.modules.messaging.domain.entities import (
    AutoreplySettings,
    QuickReply,
    WhatsAppContact,
    WhatsAppConversation,
    WhatsAppMessage,
    WhatsAppSession,
)
from restaurante.modules.messaging.domain.errors import (
    ConversationAlreadyClaimedError,
    MessageDeliveryError,
    SessionNotFoundError,
)
from restaurante.modules.messaging.domain.media import (
    MAX_MEDIA_BYTES,
    MEDIA_MESSAGE_TYPES,
    STORABLE_MIMES,
    MediaDecision,
    fits,
    media_intent,
)
from restaurante.modules.messaging.domain.ports import (
    ConversationSummary,
    MessagingRepository,
    UnsettledOrder,
    WhatsAppGateway,
)
from restaurante.modules.messaging.infrastructure.media_store import store_conversation_media
from restaurante.modules.messaging.infrastructure.models import SESSION_CONNECTED
from restaurante.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from restaurante.shared.realtime.ports import EventPublisher
from restaurante.shared.storage.ports import StorageGateway

logger = logging.getLogger(__name__)

INBOX_TOPIC = "whatsapp_inbox"

# Qué queda escrito en el hilo cuando el mensaje no es texto y no trae pie de foto.
#
# Imagen y documento ya no dicen "no soportada": el archivo se guarda y se ve en la bandeja, así
# que el marcador es sólo la frase que sostiene el hilo cuando el cliente no escribió nada. El
# resto sigue siendo un límite de alcance deliberado — ninguno tiene hoy quien lo lea.
_UNSUPPORTED_PLACEHOLDER = {
    "image": "[imagen]",
    "document": "[documento]",
    "audio": "[nota de voz recibida — no soportada todavía]",
    "video": "[video recibido — no soportado todavía]",
    "location": "[ubicación recibida — no soportada todavía]",
    "sticker": "[sticker recibido — no soportado todavía]",
}
_UNSUPPORTED_FALLBACK = "[mensaje no soportado todavía]"

MAX_REPLY_CHARS = 4096

# Con qué método se declara un pago cuyo comprobante llegó por el chat. `transfer` porque es lo que
# es: una transferencia de la que alguien mandó la captura. El método del claim no cobra nada — lo
# que cobra es la verificación, y ahí manda el método del PEDIDO.
_PROOF_FROM_CHAT_METHOD = "transfer"


@dataclass
class InboundMessage:
    """What the webhook extracted from the bridge's payload, already normalised."""

    provider_instance_ref: str
    provider_message_id: str
    from_phone: str
    body: str | None = None
    message_type: str = "text"
    sender_name: str | None = None
    # La dirección del proveedor tal cual llegó: hace falta para pedirle el archivo de este
    # mensaje, porque exige la clave entera y no sólo el id.
    provider_remote_jid: str | None = None
    # Lo que el proveedor PROMETE del archivo, sin haberlo descargado. Es lo que permite decidir
    # antes de gastar: un video de 20 MB se rechaza leyendo esto.
    media_mime: str | None = None
    media_size: int | None = None


@dataclass
class Thread:
    conversation: WhatsAppConversation
    contact: WhatsAppContact
    messages: list[WhatsAppMessage]
    holder_name: str | None = None
    #: `id de mensaje → pedido` para los archivos que YA son comprobante de alguno. Evita que dos
    #: personas peguen la misma foto a dos pedidos sin enterarse.
    proof_of: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)


class AssistantResponder(Protocol):
    """Quien contesta cuando la conversación es del asistente. Puerto LOCAL, a propósito.

    Se declara aquí y no se importa de `assistant` por el mismo motivo que el anunciante de
    alertas vive en inventario: messaging no debe conocer al asistente. Ausente → el canal
    se comporta exactamente como antes de `assistant-core`.
    """

    async def respond(
        self,
        conversation: WhatsAppConversation,
        contact_id: uuid.UUID,
        contact_phone: str,
        text: str,
    ) -> bool: ...


class PaymentClaimRecorder(Protocol):
    """Quien registra la declaración de pago. Puerto LOCAL, por lo mismo que el asistente.

    Messaging no debe conocer `orders`: aquí se declara la forma y la raíz de composición enchufa
    quien la cumple. Las reglas del claim —pedido abierto, importe positivo, techo de pendientes—
    son de `orders` y **siguen siendo suyas**: este puerto no las repite ni las relaja.
    """

    async def declare_payment(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        amount: Decimal,
        method: str,
        proof_url: str | None = None,
    ) -> Any: ...


class MessagingService:
    def __init__(
        self,
        repo: MessagingRepository,
        gateway: WhatsAppGateway,
        events: EventPublisher,
        idle_hours: int = 24,
        public_base_url: str = "",
        webhook_secret: str = "",
        autoreply: AutoreplyService | None = None,
        assistant: AssistantResponder | None = None,
        media_storage: StorageGateway | None = None,
        claims: PaymentClaimRecorder | None = None,
    ) -> None:
        self._repo = repo
        self._gateway = gateway
        self._events = events
        self._idle_hours = idle_hours
        # Cómo nos ve el puente desde fuera. El puente corre en otra máquina, así que no
        # puede ser `localhost`: tiene que ser la URL pública del tenant.
        self._public_base_url = public_base_url
        self._webhook_secret = webhook_secret
        # Opcional: sin él, el canal se comporta exactamente como antes de este change.
        self._autoreply = autoreply
        # Opcional también: sin asistente, ninguna conversación entra en modo bot y todas
        # las atiende una persona, que es como funcionaba hasta la fase 4.
        self._assistant = assistant
        # Sin almacenamiento, un archivo entrante deja su marcador y nada más — el
        # comportamiento exacto de antes de que el canal supiera recibir archivos.
        self._media_storage = media_storage
        # Quien registra la declaración de pago. Ausente → la bandeja no ofrece la acción, que es
        # el comportamiento de antes de que un comprobante pudiera nacer del chat.
        self._claims = claims

    # --- Inbound -------------------------------------------------------------
    async def handle_inbound(self, inbound: InboundMessage) -> WhatsAppMessage | None:
        """Persist an inbound message. Returns None when it was a redelivery.

        The whole method is written to be safe to call twice with the same payload:
        the contact is find-or-create, the conversation is resolved not created blindly,
        and the message insert is an insert-or-ignore on the provider's id.
        """
        session = await self._repo.find_session_by_instance_ref(
            inbound.provider_instance_ref
        )
        if session is None:
            raise SessionNotFoundError(
                "No hay una sesión de WhatsApp para esa instancia."
            )

        # Recibir un mensaje ES la definición de estar conectado, así que se corrige el
        # estado aquí también. Es la misma postura que el barrido de las alertas: el evento
        # de conexión da la latencia y puede perderse —Evolution reinició, el webhook no
        # estaba aún, un despliegue viejo—; esto es la garantía, y no puede perderse porque
        # llega por el mismo camino que el mensaje.
        if session.status != SESSION_CONNECTED:
            await self._repo.update_session(
                session.tenant_id, session.id, {"status": SESSION_CONNECTED}
            )
            logger.info(
                "Sesión %s marcada como conectada: llegó un mensaje por ella.", session.id
            )

        contact = await self._repo.find_or_create_contact(
            session.tenant_id, inbound.from_phone, inbound.sender_name
        )
        conversation = await self._resolve_conversation(session, contact.id)

        # El tipo se guarda siempre; el ARCHIVO se decide después, y sólo si esta inserción
        # gana. Una redistribución no puede volver a descargar ni volver a subir nada.
        decision = media_intent(
            inbound.message_type, inbound.media_mime, inbound.media_size
        )
        message = await self._repo.add_inbound_message_once(
            session.tenant_id,
            session.branch_id,
            conversation.id,
            content=self._inbound_content(inbound),
            provider_message_id=inbound.provider_message_id,
            provider_remote_jid=inbound.provider_remote_jid,
            media_type=(
                inbound.message_type
                if inbound.message_type in MEDIA_MESSAGE_TYPES
                else None
            ),
            media_mime=inbound.media_mime,
        )
        if message is None:
            # A redelivery. Not an error, and specifically not a second doorbell.
            logger.debug(
                "Duplicate WhatsApp delivery ignored (provider_message_id=%s)",
                inbound.provider_message_id,
            )
            return None

        # ANTES del timbre, para que el primer refresco de la bandeja ya traiga la imagen. Y
        # DESPUÉS de guardar el mensaje, que es la garantía que sostiene todo este camino: un
        # fallo bajando el archivo cuesta el archivo, nunca el mensaje.
        await self._attach_media(session, message, inbound, decision)
        await self._publish(session.tenant_id, session.branch_id, conversation.id)
        # El saludo va DESPUÉS de guardar y avisar: el mensaje del cliente ya está a salvo,
        # así que un fallo aquí cuesta un saludo, nunca el mensaje.
        await self._greet(conversation, contact.phone)
        # Y después del saludo, por si a esta conversación le toca el asistente.
        #
        # El orden importa y es sutil: `conversation` se leyó ANTES de saludar, así que si el
        # saludo acaba de ocurrir su `status` sigue diciendo `new` aquí. Es justo lo que hay
        # que querer — el mensaje que provoca el saludo no puede ser además el que acepta el
        # asistente, porque cuando lo escribió todavía no le habían ofrecido nada. Y por lo
        # mismo tampoco puede disparar una FAQ: el saludo ya lleva el enlace de la carta, y dos
        # mensajes automáticos por un entrante es exactamente el volumen que hace que WhatsApp
        # mire un número.
        handled = await self._assist(conversation, contact.id, contact.phone, message.content)
        if not handled:
            # Sólo si el asistente no era el dueño de este mensaje. Los dos caminos son casi
            # disjuntos —el asistente atiende `bot` y el opt-in; las FAQs, `greeted` a secas—,
            # pero preguntarlo aquí es lo que garantiza que nadie reciba las dos cosas.
            await self._answer_faq(conversation, contact.id, contact.phone, message.content)
        return message

    async def _attach_media(
        self,
        session: WhatsAppSession,
        message: WhatsAppMessage,
        inbound: InboundMessage,
        decision: MediaDecision,
    ) -> None:
        """Baja el archivo y lo pega al mensaje. Nunca hace fallar la recepción.

        Aislada en su propio método a propósito: es la parte que tarda, y el día que la latencia
        del webhook moleste, moverla a un worker es mover esta llamada — no reescribir el flujo.

        Cuando no se guarda nada, el mensaje se queda con su `media_type` y sin URL, y el hilo
        entonces dice "llegó una imagen y no se pudo traer". Feo y honesto.
        """
        if not decision.store:
            if inbound.message_type in MEDIA_MESSAGE_TYPES:
                # Sólo se registra cuando había algo que guardar y se decidió no hacerlo; un
                # sticker o una nota de voz no merecen una línea de log cada vez.
                logger.info(
                    "Archivo entrante no guardado (%s): %s",
                    inbound.message_type,
                    decision.reason,
                )
            return
        if self._media_storage is None:
            logger.warning(
                "Llegó un archivo pero no hay almacenamiento configurado; queda el marcador."
            )
            return
        if not inbound.provider_remote_jid:
            # Sin la clave del proveedor no hay a qué pedirle el archivo.
            logger.warning("Archivo entrante sin dirección del proveedor; no se puede pedir.")
            return
        try:
            data = await self._gateway.fetch_media(
                session, inbound.provider_message_id, inbound.provider_remote_jid
            )
        except Exception:  # noqa: BLE001 - el archivo no puede costar el mensaje
            logger.warning(
                "No se pudo traer el archivo del mensaje %s", message.id, exc_info=True
            )
            return
        url = await store_conversation_media(
            session.tenant_id,
            message.whatsapp_conversation_id,
            inbound.media_mime or "",
            data,
            storage=self._media_storage,
        )
        if url is None:
            return
        await self._repo.attach_media(session.tenant_id, message.id, url)

    async def _greet(
        self, conversation: WhatsAppConversation, contact_phone: str
    ) -> None:
        """Saludo automático, si está encendido. Nunca hace fallar la recepción."""
        if self._autoreply is None:
            return
        try:
            await self._autoreply.greet_if_new(conversation, contact_phone)
        except Exception:  # noqa: BLE001 - un saludo perdido no puede costar el mensaje
            logger.warning("El saludo automático falló", exc_info=True)

    async def _assist(
        self,
        conversation: WhatsAppConversation,
        contact_id: uuid.UUID,
        contact_phone: str,
        text: str,
    ) -> bool:
        """Deja contestar al asistente, si lo hay. `True` si el mensaje era suyo.

        Nunca hace fallar la recepción — mismo trato que el saludo: el mensaje del cliente ya
        está guardado y el timbre ya sonó, así que lo que se pierda aquí es una respuesta
        automática, nunca el mensaje. Un fallo cuenta como "no era mío", que es lo que deja pasar
        el mensaje al siguiente que sepa contestarlo.
        """
        if self._assistant is None:
            return False
        try:
            return await self._assistant.respond(
                conversation, contact_id, contact_phone, text
            )
        except Exception:  # noqa: BLE001 - una respuesta perdida no puede costar el mensaje
            logger.warning("El asistente falló al responder", exc_info=True)
            return False

    async def _answer_faq(
        self,
        conversation: WhatsAppConversation,
        contact_id: uuid.UUID,
        contact_phone: str,
        text: str,
    ) -> None:
        """Contesta una pregunta conocida, si alguna coincide. Nunca cuesta el mensaje.

        Es el tercer mecanismo automático del canal y el único que lee lo que el cliente
        escribió. Las dos puertas que lo hacen defendible viven en `AutoreplyService.answer_faq`;
        aquí sólo se garantiza que nada de esto pueda tumbar la recepción.
        """
        if self._autoreply is None:
            return
        try:
            await self._autoreply.answer_faq(
                conversation, contact_phone, contact_id, text
            )
        except Exception:  # noqa: BLE001 - una FAQ perdida no puede costar el mensaje
            logger.warning("La respuesta por palabra clave falló", exc_info=True)

    async def _publish(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> None:
        """Best-effort doorbell, rung after the message is already committed.

        Swallowed here on top of the port's own best-effort contract (mirrors delivery
        and the KDS): a broker outage must cost the live refresh and nothing else. The
        inbox still finds the message on its polling interval.
        """
        try:
            await self._events.publish(
                INBOX_TOPIC,
                tenant_id,
                branch_id,
                {"conversation_id": str(conversation_id)},
            )
        except Exception:  # noqa: BLE001 - the doorbell is a non-blocking side effect
            logger.warning("WhatsApp inbox doorbell failed", exc_info=True)

    def _inbound_content(self, inbound: InboundMessage) -> str:
        """Lo que queda escrito en el hilo.

        Si el cliente escribió algo, eso es el mensaje — **también cuando venía como pie de una
        foto**. Antes se exigía que el tipo fuera `text` y el pie se perdía; descartar lo que el
        cliente escribió es el mismo error que descartar la imagen, y encima peor: la frase es lo
        que le dice al agente de qué es el archivo.
        """
        if inbound.body:
            return inbound.body
        if inbound.message_type == "text":
            return _UNSUPPORTED_FALLBACK
        return _UNSUPPORTED_PLACEHOLDER.get(
            inbound.message_type, _UNSUPPORTED_FALLBACK
        )

    async def _resolve_conversation(
        self, session: WhatsAppSession, contact_id: uuid.UUID
    ) -> WhatsAppConversation:
        """Join the live thread, or close a stale one and start fresh."""
        existing = await self._repo.find_open_conversation(
            session.tenant_id, session.branch_id, contact_id
        )
        if existing is not None:
            if not await self._is_stale(session.tenant_id, existing):
                return existing
            await self._repo.close_conversation(session.tenant_id, existing.id)
        return await self._repo.create_conversation(
            session.tenant_id, session.branch_id, contact_id
        )

    async def _is_stale(
        self, tenant_id: uuid.UUID, conversation: WhatsAppConversation
    ) -> bool:
        activity = await self._repo.last_activity_at(tenant_id, conversation.id)
        if activity is None:
            return False
        return activity < datetime.now(UTC) - timedelta(hours=self._idle_hours)

    # --- Un comprobante que nace del chat ------------------------------------
    async def eligible_orders_for_proof(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[UnsettledOrder]:
        """Los pedidos de este contacto a los que les falta plata.

        Es lo que la bandeja ofrece al usar una imagen como comprobante. Si está vacío, la pantalla
        tiene que decir por qué en vez de pintar un botón muerto.
        """
        conversation = await self._require_conversation(
            tenant_id, branch_id, conversation_id
        )
        since = datetime.now(UTC) - timedelta(hours=max(1, self._idle_hours))
        return await self._repo.unsettled_orders_for_contact(
            tenant_id, conversation.whatsapp_contact_id, since=since
        )

    async def use_message_as_proof(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        order_id: uuid.UUID,
        amount: Decimal,
    ) -> None:
        """Convierte el archivo de un mensaje en el comprobante de un pedido.

        Lo hace una PERSONA, nunca la llegada del archivo: los clientes mandan fotos de la calle,
        memes y su cédula, y un claim creado por el simple hecho de llegar una imagen acaba siendo
        un "comprobante" que es la foto de un perro — tras lo cual el mostrador aprende a ignorar
        el aviso.

        Dos comprobaciones, y las dos importan:

        1. **El mensaje es de ESTA conversación** y tiene archivo. Un id de otro hilo no vale.
        2. **El pedido es de ESTE contacto** y le falta plata. Aceptar un id ajeno sería un salto
           entre clientes disfrazado de comodidad.

        Lo demás —pedido abierto, importe positivo, techo de pendientes— lo sigue decidiendo
        `orders`, que es de quien son esas reglas.
        """
        if self._claims is None:
            raise ValidationError("Registrar pagos no está disponible en este despliegue.")
        conversation = await self._require_conversation(
            tenant_id, branch_id, conversation_id
        )
        message = await self._repo.find_message(tenant_id, conversation_id, message_id)
        if message is None:
            raise NotFoundError("Ese mensaje no es de esta conversación.")
        if not message.media_url:
            raise ValidationError(
                "Ese mensaje no trae un archivo que se pueda usar como comprobante."
            )

        already = await self._repo.orders_using_proofs(tenant_id, [message.media_url])
        if message.media_url in already:
            # No es un fallo técnico: alguien ya lo pegó. Decirlo es lo que evita que el mismo
            # recibo cuente dos veces en dos pedidos distintos.
            raise ConflictError(
                "Ese archivo ya está usado como comprobante de otro pedido."
            )

        since = datetime.now(UTC) - timedelta(hours=max(1, self._idle_hours))
        eligible = await self._repo.unsettled_orders_for_contact(
            tenant_id, conversation.whatsapp_contact_id, since=since
        )
        target = next((o for o in eligible if o.order_id == order_id), None)
        if target is None:
            raise NotFoundError(
                "Ese pedido no es de este contacto, o ya no debe nada."
            )

        await self._claims.declare_payment(
            tenant_id,
            order_id,
            amount,
            _PROOF_FROM_CHAT_METHOD,
            proof_url=message.media_url,
        )

    # --- Inbox reads ---------------------------------------------------------
    async def list_conversations(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        include_closed: bool = False,
    ) -> list[ConversationSummary]:
        return await self._repo.list_conversations(
            tenant_id, branch_id, include_closed=include_closed
        )

    async def get_thread(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> Thread:
        conversation = await self._require_conversation(
            tenant_id, branch_id, conversation_id
        )
        contact = await self._repo.get_contact(
            tenant_id, conversation.whatsapp_contact_id
        )
        if contact is None:
            raise NotFoundError("El contacto de la conversación no existe.")
        messages = await self._repo.list_messages(tenant_id, conversation_id)
        holder = (
            await self._repo.employee_display_name(tenant_id, conversation.employee_id)
            if conversation.employee_id
            else None
        )
        used = await self._repo.orders_using_proofs(
            tenant_id, [m.media_url for m in messages if m.media_url]
        )
        return Thread(
            proof_of={
                m.id: used[m.media_url]
                for m in messages
                if m.media_url and m.media_url in used
            },
            conversation=conversation,
            contact=contact,
            messages=messages,
            holder_name=holder,
        )

    async def _require_conversation(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> WhatsAppConversation:
        conversation = await self._repo.get_conversation(tenant_id, conversation_id)
        # Branch mismatch reads as "not found", not "forbidden": an inbox scoped to one
        # branch should not confirm that a conversation exists on another.
        if conversation is None or conversation.branch_id != branch_id:
            raise NotFoundError("La conversación no existe en esta sucursal.")
        return conversation

    # --- Inbox writes --------------------------------------------------------
    async def claim(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
        employee_id: uuid.UUID,
    ) -> WhatsAppConversation:
        await self._require_conversation(tenant_id, branch_id, conversation_id)
        claimed = await self._repo.claim_conversation(
            tenant_id, conversation_id, employee_id
        )
        if claimed is not None:
            return claimed

        # Lost the race (or it is closed). Re-read to say precisely which.
        current = await self._repo.get_conversation(tenant_id, conversation_id)
        if current is None:
            raise NotFoundError("La conversación no existe en esta sucursal.")
        if current.status == "closed":
            raise ConflictError("La conversación ya está cerrada.")
        if current.employee_id == employee_id:
            # Already ours: claiming twice is a no-op, not a conflict.
            return current
        holder_name = (
            await self._repo.employee_display_name(tenant_id, current.employee_id)
            if current.employee_id
            else None
        )
        raise ConversationAlreadyClaimedError(
            holder_employee_id=str(current.employee_id) if current.employee_id else None,
            holder_name=holder_name,
        )

    async def send_reply(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
        employee_id: uuid.UUID,
        body: str,
    ) -> WhatsAppMessage:
        text = body.strip()
        if not text:
            raise ValidationError("El mensaje no puede estar vacío.")
        if len(text) > MAX_REPLY_CHARS:
            raise ValidationError(
                f"El mensaje supera los {MAX_REPLY_CHARS} caracteres."
            )

        conversation = await self._require_conversation(
            tenant_id, branch_id, conversation_id
        )
        if conversation.status == "closed":
            raise ConflictError(
                "La conversación está cerrada; reábrela para poder responder."
            )

        contact = await self._repo.get_contact(
            tenant_id, conversation.whatsapp_contact_id
        )
        if contact is None:
            raise NotFoundError("El contacto de la conversación no existe.")

        session = await self._repo.get_session_for_branch(tenant_id, branch_id)
        if session is None:
            raise SessionNotFoundError(
                "Esta sucursal no tiene un número de WhatsApp vinculado."
            )

        # Persist first: a reply that vanishes into a dead bridge must still be in the
        # thread. Sending first and persisting after loses the record exactly when the
        # agent most needs to see it.
        message = await self._repo.add_message(
            tenant_id,
            branch_id,
            conversation_id,
            sender_type="employee",
            content=text,
            employee_id=employee_id,
            delivery_state="pending",
        )

        try:
            provider_message_id = await self._gateway.send_text(
                session, contact.phone, text
            )
        except MessageDeliveryError:
            await self._repo.mark_delivery(
                tenant_id, message.id, delivery_state="failed"
            )
            raise

        settled = await self._repo.mark_delivery(
            tenant_id,
            message.id,
            delivery_state="sent",
            provider_message_id=provider_message_id or None,
        )
        return settled or message

    async def send_media_reply(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
        employee_id: uuid.UUID,
        data: bytes,
        *,
        mimetype: str,
        filename: str,
        caption: str = "",
    ) -> WhatsAppMessage:
        """Manda un archivo al cliente y lo deja en el hilo.

        Mismo orden que `send_reply` y por la misma razón: **se persiste antes de transmitir**. Un
        archivo que se traga un puente caído tiene que seguir estando en el hilo, o el agente cree
        que lo mandó.

        Y se guarda en R2 ANTES de enviarlo, no después: si se subiera al final, un envío correcto
        seguido de un R2 caído dejaría en el hilo un mensaje que el cliente sí recibió y que aquí
        no se puede ver. Al revés —guardado y no enviado— el estado `failed` ya lo cuenta.
        """
        if mimetype not in STORABLE_MIMES:
            raise ValidationError(
                "Sólo se pueden mandar imágenes (PNG, JPG, WEBP) o PDF."
            )
        if not fits(data):
            raise ValidationError(
                f"El archivo pesa demasiado (máximo {MAX_MEDIA_BYTES // (1024 * 1024)} MB)."
            )

        conversation = await self._require_conversation(
            tenant_id, branch_id, conversation_id
        )
        if conversation.status == "closed":
            raise ConflictError(
                "La conversación está cerrada; reábrela para poder responder."
            )
        contact = await self._repo.get_contact(
            tenant_id, conversation.whatsapp_contact_id
        )
        if contact is None:
            raise NotFoundError("El contacto de la conversación no existe.")
        session = await self._repo.get_session_for_branch(tenant_id, branch_id)
        if session is None:
            raise SessionNotFoundError(
                "Esta sucursal no tiene un número de WhatsApp vinculado."
            )

        message = await self._repo.add_message(
            tenant_id,
            branch_id,
            conversation_id,
            sender_type="employee",
            content=caption.strip(),
            employee_id=employee_id,
            delivery_state="pending",
            media_type="image" if mimetype.startswith("image/") else "document",
            media_mime=mimetype,
        )
        if self._media_storage is not None:
            url = await store_conversation_media(
                tenant_id, conversation_id, mimetype, data, storage=self._media_storage
            )
            if url:
                await self._repo.attach_media(tenant_id, message.id, url)

        try:
            provider_message_id = await self._gateway.send_media(
                session,
                contact.phone,
                data,
                mimetype=mimetype,
                filename=filename,
                caption=caption.strip(),
            )
        except MessageDeliveryError:
            await self._repo.mark_delivery(
                tenant_id, message.id, delivery_state="failed"
            )
            raise

        settled = await self._repo.mark_delivery(
            tenant_id,
            message.id,
            delivery_state="sent",
            provider_message_id=provider_message_id or None,
        )
        return settled or message

    async def send_menu_link(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
        employee_id: uuid.UUID,
    ) -> str:
        """Manda el enlace a la carta a mano, con su token.

        El equivalente humano del saludo. Existe para la conversación que ya no es `new`
        —el cliente pide la carta a mitad de charla— y para el negocio que tiene el saludo
        apagado. Pegar un enlace a mano no serviría: sin token el checkout llega vacío, y
        copiado de otra sede lleva a la carta equivocada.
        """
        conversation = await self._require_conversation(
            tenant_id, branch_id, conversation_id
        )
        if conversation.status == "closed":
            raise ConflictError(
                "La conversación está cerrada; reábrela para poder escribir."
            )
        if self._autoreply is None:
            raise ConflictError("Las respuestas automáticas no están configuradas.")
        contact = await self._repo.get_contact(
            tenant_id, conversation.whatsapp_contact_id
        )
        if contact is None:
            raise NotFoundError("El contacto de la conversación no existe.")
        return await self._autoreply.send_menu_link(
            conversation, contact.phone, employee_id
        )

    # --- Autoreply settings --------------------------------------------------
    async def autoreply_settings(self, tenant_id: uuid.UUID) -> AutoreplySettings:
        if self._autoreply is None:
            return AutoreplySettings(tenant_id=tenant_id)
        return await self._autoreply.settings_for(tenant_id)

    async def save_autoreply_settings(
        self, settings: AutoreplySettings
    ) -> AutoreplySettings:
        if self._autoreply is None:
            raise ConflictError("Las respuestas automáticas no están configuradas.")
        return await self._autoreply.save_settings(settings)

    async def quick_replies(self, tenant_id: uuid.UUID) -> list[QuickReply]:
        """Las plantillas guardadas del tenant. Sin autoreply montado, ninguna.

        Lista vacía y no un error, al contrario que guardar: no poder ver las plantillas no puede
        impedirle a nadie responder un chat.
        """
        if self._autoreply is None:
            return []
        return await self._autoreply.quick_replies_for(tenant_id)

    async def close(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> WhatsAppConversation:
        await self._require_conversation(tenant_id, branch_id, conversation_id)
        closed = await self._repo.close_conversation(tenant_id, conversation_id)
        if closed is None:
            raise NotFoundError("La conversación no existe en esta sucursal.")
        return closed

    async def resolve_acting_employee(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, branch_id: uuid.UUID
    ) -> uuid.UUID:
        employee_id = await self._repo.employee_id_for_user(
            tenant_id, user_id, branch_id
        )
        if employee_id is None:
            raise ConflictError(
                "Tu usuario no está vinculado a un empleado activo de esta sucursal."
            )
        return employee_id

    # --- Sessions ------------------------------------------------------------
    async def list_sessions(self, tenant_id: uuid.UUID) -> list[WhatsAppSession]:
        return await self._repo.list_sessions(tenant_id)

    async def create_session(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, provider_instance_ref: str
    ) -> WhatsAppSession:
        if not await self._repo.branch_exists(tenant_id, branch_id):
            raise NotFoundError("La sucursal no existe.")
        if await self._repo.get_session_for_branch(tenant_id, branch_id) is not None:
            raise ConflictError("Esta sucursal ya tiene una sesión de WhatsApp.")
        ref = provider_instance_ref.strip()
        if not ref:
            raise ValidationError("La referencia de instancia no puede estar vacía.")
        return await self._repo.create_session(tenant_id, branch_id, ref)

    async def start_pairing(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> tuple[WhatsAppSession, str | None]:
        """Pide el QR al puente y deja la sesión esperando el escaneo.

        Devuelve `(sesión, qr)`. El QR es None cuando el número ya está conectado — no hay
        nada que escanear, y decirlo es mejor que pintar un recuadro vacío.

        Si el puente falla, la sesión NO se marca `qr_pending`: mostrar "esperando escaneo"
        cuando no hay QR que escanear es una mentira que deja al usuario esperando.
        """
        session = await self._require_session(tenant_id, session_id)
        if session.status == "banned":
            raise ConflictError(
                "Este número fue bloqueado por el proveedor; hay que vincular otro."
            )
        qr = await self._gateway.start_pairing(
            session, self._webhook_url_for(session), self._webhook_secret
        )
        # Ya conectada: se refleja tal cual en vez de retroceder a `qr_pending`.
        status = "connected" if qr is None else "qr_pending"
        updated = await self._repo.update_session(
            tenant_id, session_id, {"status": status}
        )
        return (updated or session), qr

    def _webhook_url_for(self, session: WhatsAppSession) -> str:
        return (
            f"{self._public_base_url.rstrip('/')}"
            f"/webhooks/whatsapp/{session.provider_instance_ref}"
        )

    async def apply_delivery_report(
        self,
        provider_instance_ref: str,
        *,
        provider_message_id: str,
        state: str,
    ) -> bool:
        """Aplica un acuse resolviendo el tenant por la instancia. `True` si cambió algo.

        Mismo camino que `apply_status_by_instance`: el webhook no tiene subdominio, así que la
        referencia de instancia ES la prueba de a qué tenant pertenece esto.

        **Instancia desconocida o id desconocido devuelven `False`, no excepción.** El puente
        reporta también los mensajes que el dueño escribe desde su propio teléfono, y ésos no
        están en nuestra base ni deben estarlo: no encontrarlos es lo normal, no un fallo.
        """
        session = await self._repo.find_session_by_instance_ref(provider_instance_ref)
        if session is None:
            return False
        return await self._repo.apply_delivery_report(
            session.tenant_id, provider_message_id, state
        )

    async def apply_status_by_instance(
        self,
        provider_instance_ref: str,
        *,
        status: str,
        phone_number: str | None = None,
    ) -> WhatsAppSession:
        """Aplica un estado que llegó por webhook, resolviendo la sesión por su instancia.

        El webhook no tiene subdominio del que sacar el tenant, así que —igual que con los
        mensajes entrantes— la referencia de instancia ES la prueba: es única y la genera el
        puente, no es adivinable.

        El teléfono sólo se escribe si viene y aún no lo teníamos: al vincular sólo se sabe
        la referencia, y el número llega con la conexión.
        """
        session = await self._repo.find_session_by_instance_ref(provider_instance_ref)
        if session is None:
            raise SessionNotFoundError(
                f"No hay sesión para la instancia {provider_instance_ref}"
            )
        return await self.apply_status_update(
            session.tenant_id,
            session.id,
            status=status,
            phone_number=phone_number or session.phone_number,
        )

    async def apply_status_update(
        self,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        *,
        status: str,
        phone_number: str | None = None,
    ) -> WhatsAppSession:
        """Record what the provider says about a session's connection.

        Our column is a cache of the bridge's truth and can lag behind it; that gap is
        a known risk, turned into an alert by change 3.
        """
        from restaurante.modules.messaging.infrastructure.models import (
            SESSION_STATUSES,
        )

        if status not in SESSION_STATUSES:
            raise ValidationError(f"Estado de sesión desconocido: {status}")
        await self._require_session(tenant_id, session_id)
        changes: dict[str, object] = {
            "status": status,
            "last_seen_at": datetime.now(UTC),
        }
        if phone_number:
            changes["phone_number"] = phone_number
        updated = await self._repo.update_session(tenant_id, session_id, changes)
        if updated is None:
            raise SessionNotFoundError("La sesión de WhatsApp no existe.")
        return updated

    async def _require_session(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> WhatsAppSession:
        session = await self._repo.get_session(tenant_id, session_id)
        if session is None:
            raise SessionNotFoundError("La sesión de WhatsApp no existe.")
        return session
