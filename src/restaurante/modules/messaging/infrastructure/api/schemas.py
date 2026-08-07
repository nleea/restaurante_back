"""Request/response schemas for the messaging API."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, Field

from restaurante.modules.messaging.application.use_cases.manage_messaging import (
    MAX_REPLY_CHARS,
    InboundMessage,
    Thread,
)
from restaurante.modules.messaging.domain.delivery import state_from_provider
from restaurante.modules.messaging.domain.entities import (
    AutoreplySettings,
    FaqEntry,
    QuickReply,
)
from restaurante.modules.messaging.domain.ports import ConversationSummary
from restaurante.modules.messaging.domain.quick_reply import (
    MAX_QUICK_REPLY_CHARS,
    MAX_QUICK_REPLY_NAME_CHARS,
)
from restaurante.shared.domain.order_label import order_label


# --- Sessions ---------------------------------------------------------------
class SessionResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    provider_instance_ref: str
    status: str
    phone_number: str | None
    last_seen_at: datetime | None


class PairingResponse(BaseModel):
    """La sesión más el QR a escanear.

    `qr` es None cuando el número ya está conectado — no hay nada que escanear, y decirlo
    es más útil que pintar un recuadro vacío.
    """

    session: SessionResponse
    qr: str | None = None


class CreateSessionRequest(BaseModel):
    branch_id: uuid.UUID
    provider_instance_ref: str = Field(min_length=1, max_length=120)


class SessionStatusRequest(BaseModel):
    status: str
    phone_number: str | None = None


# --- Inbox ------------------------------------------------------------------
class ConversationResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str | None
    contact_phone: str
    status: str
    employee_id: uuid.UUID | None
    holder_name: str | None
    started_at: datetime
    closed_at: datetime | None
    last_message_at: datetime | None
    last_message_preview: str | None
    last_message_sender_type: str | None
    message_count: int
    # Derived, not stored: the contact spoke last, so somebody owes them an answer.
    awaiting_reply: bool

    @classmethod
    def from_summary(cls, summary: ConversationSummary) -> ConversationResponse:
        c = summary.conversation
        return cls(
            id=c.id,
            branch_id=c.branch_id,
            contact_id=summary.contact.id,
            contact_name=summary.contact.name,
            contact_phone=summary.contact.phone,
            status=c.status,
            employee_id=c.employee_id,
            holder_name=summary.holder_name,
            started_at=c.started_at,
            closed_at=c.closed_at,
            last_message_at=summary.last_message_at,
            last_message_preview=summary.last_message_preview,
            last_message_sender_type=summary.last_message_sender_type,
            message_count=summary.message_count,
            awaiting_reply=summary.awaiting_reply,
        )


class MessageResponse(BaseModel):
    id: uuid.UUID
    sender_type: str
    employee_id: uuid.UUID | None
    content: str
    delivery_state: str
    sent_at: datetime
    # `media_type` sin `media_url` = llegó un archivo y no se pudo traer. La bandeja tiene que
    # poder decirlo con palabras en vez de pintar una imagen rota.
    media_type: str | None = None
    media_mime: str | None = None
    media_url: str | None = None
    # La etiqueta del pedido del que este archivo YA es comprobante. Que la bandeja lo diga es lo
    # que evita que la misma foto se pegue a dos pedidos.
    proof_of_order: str | None = None


class ThreadResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str | None
    contact_phone: str
    status: str
    employee_id: uuid.UUID | None
    holder_name: str | None
    started_at: datetime
    closed_at: datetime | None
    messages: list[MessageResponse]

    @classmethod
    def from_thread(cls, thread: Thread) -> ThreadResponse:
        c = thread.conversation
        return cls(
            id=c.id,
            branch_id=c.branch_id,
            contact_id=thread.contact.id,
            contact_name=thread.contact.name,
            contact_phone=thread.contact.phone,
            status=c.status,
            employee_id=c.employee_id,
            holder_name=thread.holder_name,
            started_at=c.started_at,
            closed_at=c.closed_at,
            messages=[
                MessageResponse(
                    id=m.id,
                    sender_type=m.sender_type,
                    employee_id=m.employee_id,
                    content=m.content,
                    delivery_state=m.delivery_state,
                    sent_at=m.sent_at,
                    media_type=m.media_type,
                    media_mime=m.media_mime,
                    media_url=m.media_url,
                    proof_of_order=(
                        order_label(thread.proof_of[m.id])
                        if m.id in thread.proof_of
                        else None
                    ),
                )
                for m in thread.messages
            ],
        )


class EligibleOrderResponse(BaseModel):
    """Un pedido al que se le puede pegar un comprobante, con lo que hace falta para elegirlo."""

    order_id: uuid.UUID
    number: str
    total: Decimal
    balance: Decimal


class UseAsProofRequest(BaseModel):
    order_id: uuid.UUID
    # Lo declarado. Llega precargado con el saldo y se puede corregir: quien pulsa está mirando el
    # recibo, así que corregirlo le cuesta nada y al sistema adivinarlo le es imposible.
    amount: Decimal = Field(gt=0)


class ReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_REPLY_CHARS)


# --- Autoreply settings -----------------------------------------------------
class StatusMessageSchema(BaseModel):
    """Un aviso de estado: si habla, y con qué texto."""

    enabled: bool = False
    text: str = Field(default="", max_length=MAX_REPLY_CHARS)


class FaqSchema(BaseModel):
    """Una FAQ por palabra clave. El orden de la lista es la prioridad de coincidencia."""

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(default="", max_length=80)
    triggers: list[str] = Field(default_factory=list, max_length=40)
    text: str = Field(default="", max_length=MAX_REPLY_CHARS)
    enabled: bool = False

    @classmethod
    def from_entry(cls, faq: FaqEntry) -> FaqSchema:
        return cls(
            id=faq.id,
            name=faq.name,
            triggers=list(faq.triggers),
            text=faq.text,
            enabled=faq.enabled,
        )

    def to_entry(self) -> FaqEntry:
        return FaqEntry(
            id=self.id,
            name=self.name,
            triggers=list(self.triggers),
            text=self.text,
            enabled=self.enabled,
        )


class QuickReplySchema(BaseModel):
    """Una plantilla que un empleado inserta en el compositor. No dispara sola nunca.

    Sin `enabled` y sin `triggers`, al contrario que `FaqSchema`: los dos sólo significan algo
    cuando algo lee el mensaje del cliente y decide contestar, y aquí decide una persona.
    """

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(default="", max_length=MAX_QUICK_REPLY_NAME_CHARS)
    text: str = Field(default="", max_length=MAX_QUICK_REPLY_CHARS)

    @classmethod
    def from_entry(cls, entry: QuickReply) -> QuickReplySchema:
        return cls(id=entry.id, name=entry.name, text=entry.text)

    def to_entry(self) -> QuickReply:
        return QuickReply(id=self.id, name=self.name, text=self.text)


class QuickRepliesResponse(BaseModel):
    """Lo que ve el inbox: la lista guardada y nada más.

    Sin sugeridas a propósito (ver `design.md` §6): las sugeridas son cosa del editor, y enseñarle
    al mesero unas plantillas que el dueño nunca aprobó es poner palabras en boca del negocio.
    """

    quick_replies: list[QuickReplySchema]


class AutoreplySettingsSchema(BaseModel):
    """Cómo responde solo el negocio. Un tenant sin fila lee esto con todo apagado."""

    greeting_enabled: bool = False
    greeting_open_text: str = Field(default="", max_length=MAX_REPLY_CHARS)
    greeting_closed_text: str = Field(default="", max_length=MAX_REPLY_CHARS)
    # Tercera variante, para el contacto con un pedido esperando pago. Vacía cae a las otras.
    greeting_awaiting_payment_text: str = Field(default="", max_length=MAX_REPLY_CHARS)
    assistant_offer_enabled: bool = False
    idle_hours: int = Field(default=24, ge=1, le=720)
    token_lifetime_hours: int = Field(default=24, ge=1, le=720)
    status_mapping: dict[str, StatusMessageSchema] = Field(default_factory=dict)
    # `null` = este tenant nunca las tocó (se le ofrecen las sugeridas, apagadas); `[]` = decidió
    # que ninguna. La distinción viaja hasta la pantalla: sin ella, borrarlas todas no se puede
    # guardar y una FAQ borrada resucita en la siguiente carga.
    faqs: list[FaqSchema] | None = None
    # Mismo `null` ≠ `[]`, y aquí el que resucitaría es una plantilla borrada.
    quick_replies: list[QuickReplySchema] | None = None

    @classmethod
    def from_settings(cls, settings: AutoreplySettings) -> AutoreplySettingsSchema:
        mapping: dict[str, StatusMessageSchema] = {}
        for state, entry in settings.status_mapping.items():
            if isinstance(entry, dict):
                mapping[state] = StatusMessageSchema(
                    enabled=bool(entry.get("enabled", False)),
                    text=str(entry.get("text") or ""),
                )
        return cls(
            greeting_enabled=settings.greeting_enabled,
            greeting_open_text=settings.greeting_open_text,
            greeting_closed_text=settings.greeting_closed_text,
            greeting_awaiting_payment_text=settings.greeting_awaiting_payment_text,
            assistant_offer_enabled=settings.assistant_offer_enabled,
            idle_hours=settings.idle_hours,
            token_lifetime_hours=settings.token_lifetime_hours,
            status_mapping=mapping,
            faqs=(
                None
                if settings.faqs is None
                else [FaqSchema.from_entry(faq) for faq in settings.faqs]
            ),
            quick_replies=(
                None
                if settings.quick_replies is None
                else [QuickReplySchema.from_entry(e) for e in settings.quick_replies]
            ),
        )

    def to_settings(self, tenant_id: uuid.UUID) -> AutoreplySettings:
        return AutoreplySettings(
            tenant_id=tenant_id,
            greeting_enabled=self.greeting_enabled,
            greeting_open_text=self.greeting_open_text,
            greeting_closed_text=self.greeting_closed_text,
            greeting_awaiting_payment_text=self.greeting_awaiting_payment_text,
            assistant_offer_enabled=self.assistant_offer_enabled,
            idle_hours=self.idle_hours,
            token_lifetime_hours=self.token_lifetime_hours,
            status_mapping={
                state: {"enabled": entry.enabled, "text": entry.text}
                for state, entry in self.status_mapping.items()
            },
            faqs=(
                None if self.faqs is None else [faq.to_entry() for faq in self.faqs]
            ),
            quick_replies=(
                None
                if self.quick_replies is None
                else [entry.to_entry() for entry in self.quick_replies]
            ),
        )


class AutoreplyDefaultsResponse(BaseModel):
    """Los ajustes vigentes más lo que la pantalla necesita para editarlos sin adivinar."""

    settings: AutoreplySettingsSchema
    default_status_mapping: dict[str, StatusMessageSchema]
    # Las sugeridas, para el botón "Restaurar sugeridas" y para el tenant que nunca las tocó.
    # Llegan apagadas: instalar esto no puede cambiarle el canal a nadie sin que lo pida.
    suggested_faqs: list[FaqSchema]
    # Las plantillas sugeridas, para el botón "Usar las sugeridas" del tenant que nunca las tocó.
    # Adoptarlas rellena el formulario y NO guarda: irse sin guardar lo deja como estaba.
    suggested_quick_replies: list[QuickReplySchema]
    greeting_placeholders: list[str]
    order_placeholders: list[str]
    faq_placeholders: list[str]
    awaiting_payment_placeholders: list[str]
    # Si el asistente conversacional existe. Falso hasta `assistant-core`, y la pantalla lo
    # usa para deshabilitar la oferta: un saludo no puede anunciar algo que no va a contestar.
    assistant_available: bool = False


class MenuLinkResponse(BaseModel):
    """El enlace que acaba de salir, para que el agente vea qué mandó."""

    link: str
    thread: ThreadResponse


# --- Webhook ----------------------------------------------------------------
# El tipo de mensaje de Baileys (lo que Evolution manda en `data.messageType`) traducido a
# nuestro vocabulario. Lo que no esté aquí cae en "unsupported" y se guarda como marcador.
_BAILEYS_TEXT_TYPES = frozenset({"conversation", "extendedTextMessage"})
_BAILEYS_MEDIA_TYPES = {
    "imageMessage": "image",
    "audioMessage": "audio",
    "videoMessage": "video",
    "documentMessage": "document",
    "documentWithCaptionMessage": "document",
    "locationMessage": "location",
    "liveLocationMessage": "location",
    "stickerMessage": "sticker",
    "contactMessage": "contact",
    "ptvMessage": "video",
}
# Sufijos del JID de WhatsApp. `remoteJid` llega como "573001112233@s.whatsapp.net".
_JID_SUFFIXES = ("@s.whatsapp.net", "@c.us", "@g.us", "@lid")


def _phone_from_jid(jid: str) -> str:
    """A quién le respondemos, sacado del JID.

    Normalmente el JID es `<número>@s.whatsapp.net` y nos quedamos con el número.

    Pero WhatsApp también manda `@lid`, un identificador de privacidad que **no es un
    teléfono**: quitarle el sufijo deja una cifra sin sentido, y Evolution le pegaría
    `@s.whatsapp.net` al enviar (ver `createJid`), apuntando a un usuario inexistente.
    Por eso un `@lid` se conserva ENTERO — es lo único con lo que se le puede responder.

    El precio es que de esos contactos no sabemos el teléfono. Es la verdad: WhatsApp no
    nos lo dio.
    """
    if jid.endswith("@lid"):
        return jid
    local = jid.split("@", 1)[0]
    # Un JID puede traer ":12" (id de dispositivo) pegado al número.
    return local.split(":", 1)[0]


class WebhookMessagePayload(BaseModel):
    """La notificación entrante del puente, normalizada en el borde.

    Soporta dos formas a propósito:

    - **Evolution API** (el puente elegido): un sobre `{event, instance, data, …}` con el
      mensaje anidado en `data`, en formato Baileys (`data.key.id`,
      `data.key.remoteJid`, `data.message.conversation`).
    - **Plana** (`{id, from, text}`): la que usan otros puentes y nuestros tests.

    Toda la traducción vive aquí, así que cambiar de puente no toca el servicio.
    """

    model_config = {"extra": "allow"}

    # --- Sobre de Evolution -------------------------------------------------
    event: str | None = None
    data: dict[str, Any] | None = None

    # --- Forma plana --------------------------------------------------------
    id: str | None = None
    message_id: str | None = None
    # `from` is a keyword, so the field is `from_`. The alias must be attached via
    # Annotated: with `from __future__ import annotations` a bare `Field(alias=...)`
    # is silently ignored by Pydantic, which would drop every sender phone.
    from_: Annotated[str | None, Field(alias="from")] = None
    phone: str | None = None
    text: str | None = None
    body: str | None = None
    type: str = "text"
    sender_name: str | None = None
    push_name: str | None = None

    def to_inbound(self, instance_ref: str) -> InboundMessage | None:
        """None cuando el payload no es un mensaje entrante que podamos guardar."""
        if self.data is not None:
            return self._evolution_inbound(instance_ref)
        return self._flat_inbound(instance_ref)

    # --- Evolution ----------------------------------------------------------
    def _evolution_inbound(self, instance_ref: str) -> InboundMessage | None:
        # Evolution manda TODOS sus eventos a la misma URL (conexión, QR, presencia…).
        # Sólo `messages.upsert` es un mensaje.
        if self.event is not None and self.event != "messages.upsert":
            return None
        data = self.data or {}
        key = data.get("key") or {}
        if not isinstance(key, dict):
            return None

        # Evolution reenvía también NUESTROS propios envíos. Guardarlos duplicaría cada
        # respuesta que mandamos, y encima como si la hubiera escrito el cliente.
        if key.get("fromMe") is True:
            return None

        provider_message_id = key.get("id")
        # Cuando el JID es un `@lid`, WhatsApp puede mandar aparte el JID real en
        # `remoteJidAlt`. Evolution ya lo sustituye cuando existe, pero preferirlo aquí
        # también cubre las veces que no lo hizo — y ese sí trae el teléfono de verdad.
        remote_jid = key.get("remoteJidAlt") or key.get("remoteJid")
        if not provider_message_id or not remote_jid:
            return None
        # Los grupos no son una conversación de atención: un pedido no llega por un grupo,
        # y responder ahí escribiría delante de gente que no pidió nada.
        if str(remote_jid).endswith("@g.us"):
            return None

        message = data.get("message")
        message = message if isinstance(message, dict) else {}
        raw_type = str(data.get("messageType") or "")
        body = _evolution_text(message)
        if raw_type in _BAILEYS_TEXT_TYPES or (not raw_type and body):
            message_type = "text"
        else:
            message_type = _BAILEYS_MEDIA_TYPES.get(raw_type, "unsupported")

        media_mime, media_size = _evolution_media(message, raw_type)
        return InboundMessage(
            provider_instance_ref=instance_ref,
            provider_message_id=str(provider_message_id),
            from_phone=_phone_from_jid(str(remote_jid)),
            body=body,
            message_type=message_type,
            sender_name=data.get("pushName") or None,
            # La clave del proveedor, para poder pedirle el archivo después. Se guarda tal cual.
            provider_remote_jid=str(remote_jid),
            media_mime=media_mime,
            media_size=media_size,
        )

    # --- Forma plana --------------------------------------------------------
    def _flat_inbound(self, instance_ref: str) -> InboundMessage | None:
        provider_message_id = self.id or self.message_id
        phone = self.from_ or self.phone
        if not provider_message_id or not phone:
            return None
        return InboundMessage(
            provider_instance_ref=instance_ref,
            provider_message_id=provider_message_id,
            from_phone=phone,
            body=self.text or self.body,
            message_type=self.type or "text",
            sender_name=self.sender_name or self.push_name,
        )


def _evolution_text(message: dict[str, Any]) -> str | None:
    """El texto de un mensaje Baileys, esté donde esté — incluido el pie de foto.

    El pie cuenta como texto del mensaje a propósito: descartar lo que el cliente escribió es el
    mismo error que descartar la imagen, y encima es el que más duele — la frase es justo lo que le
    dice al agente de qué es la foto ("aquí va mi comprobante del pedido A3F2").
    """
    conversation = message.get("conversation")
    if isinstance(conversation, str) and conversation:
        return conversation
    extended = message.get("extendedTextMessage")
    if isinstance(extended, dict):
        text = extended.get("text")
        if isinstance(text, str) and text:
            return text
    for key in _CAPTIONED_TYPES:
        holder = message.get(key)
        if isinstance(holder, dict):
            caption = holder.get("caption")
            if isinstance(caption, str) and caption:
                return caption
    return None


#: Dónde vive un pie de foto en Baileys. El orden no importa: sólo uno existe por mensaje.
_CAPTIONED_TYPES = (
    "imageMessage",
    "documentMessage",
    "documentWithCaptionMessage",
    "videoMessage",
)


def _evolution_media(message: dict[str, Any], raw_type: str) -> tuple[str | None, int | None]:
    """`(mimetype, tamaño)` que el proveedor promete para el archivo, sin descargarlo.

    Es lo que hace posible decidir antes de gastar: un video de 20 MB se rechaza leyendo esto.
    Devuelve `(None, None)` cuando el mensaje no trae archivo — o cuando el puente no lo dijo, que
    no es motivo para rechazar (ver `media_intent`).
    """
    holder = message.get(raw_type)
    # `documentWithCaptionMessage` envuelve el documento de verdad una capa más adentro.
    if isinstance(holder, dict) and "message" in holder:
        inner = holder.get("message")
        if isinstance(inner, dict):
            nested = inner.get("documentMessage")
            if isinstance(nested, dict):
                holder = nested
    if not isinstance(holder, dict):
        return None, None
    mimetype = holder.get("mimetype")
    length = holder.get("fileLength")
    if isinstance(length, str) and length.isdigit():
        length = int(length)
    return (
        mimetype if isinstance(mimetype, str) and mimetype else None,
        length if isinstance(length, int) else None,
    )


# Cómo llama Evolution a los estados de conexión, traducido a los nuestros.
#
# `open` es el único que significa "está recibiendo". `connecting` incluye el rato en que hay
# un QR en pantalla esperando; `close` es que se cayó o la cerraron desde el teléfono.
_EVOLUTION_STATES = {
    "open": "connected",
    "connecting": "qr_pending",
    "close": "disconnected",
    "refused": "banned",
}


class ConnectionUpdate(BaseModel):
    """Un cambio de estado del número, tal y como lo cuenta el puente.

    Existe porque sin esto el estado de una sesión NO SE ACTUALIZA NUNCA: se quedaba en
    `qr_pending` desde que se pidió el QR, aunque el número llevara días recibiendo mensajes.
    El único camino para cambiarlo era que una persona llamara al endpoint a mano.
    """

    status: str
    phone_number: str | None = None


def connection_update(payload: WebhookMessagePayload) -> ConnectionUpdate | None:
    """El cambio de estado que trae el sobre, o `None` si no es uno.

    Evolution manda TODOS sus eventos a la misma URL, así que la mayoría no son esto.
    """
    if payload.event != "connection.update":
        return None
    data = payload.data or {}
    raw_state = str(data.get("state") or data.get("connection") or "")
    status = _EVOLUTION_STATES.get(raw_state)
    if status is None:
        return None
    # Al conectar, Evolution suele decir de qué número se trata (`wuid`). Es la primera vez
    # que lo sabemos: al vincular sólo teníamos la referencia de la instancia.
    wuid = data.get("wuid") or data.get("owner")
    phone = _phone_from_jid(str(wuid)) if isinstance(wuid, str) and wuid else None
    return ConnectionUpdate(status=status, phone_number=phone)


class DeliveryReport(BaseModel):
    """Un acuse de UN mensaje NUESTRO, ya traducido a nuestra escala.

    Sale de `MESSAGES_UPDATE`, que es el evento que faltaba para tener ✓✓ en el hilo.
    """

    provider_message_id: str
    state: str


def delivery_update(payload: WebhookMessagePayload) -> DeliveryReport | None:
    """El acuse que trae el sobre, o `None` si no es uno.

    El sobre de Evolution v2.3.7, leído de su código
    (`src/api/integrations/channel/whatsapp/whatsapp.baileys.service.ts`) y no de memoria:

        {"event": "messages.update",
         "data": {"keyId": "3EB0…", "remoteJid": "…", "fromMe": true,
                  "status": "DELIVERY_ACK", "instanceId": "…"}}

    Tres filtros, y los tres son necesarios:

    1. **El evento**, porque el puente manda todos a la misma URL.
    2. **`fromMe`**, porque el acuse viaja igual para los mensajes del CLIENTE y ésos no llevan
       palomitas: nadie enseña "leído" sobre el mensaje de otro. Es una trampa ya conocida de este
       canal — `_evolution_inbound` tiene el filtro simétrico por la misma razón.
    3. **El estado traducible**: un `ERROR`, o un valor que el puente añada mañana, es silencio.
    """
    if payload.event != "messages.update":
        return None
    data = payload.data or {}
    if data.get("fromMe") is not True:
        return None
    # `keyId` es lo normal. `messageId` lo manda cuando además encontró el mensaje en su propia
    # base y resolvió el id original de un protocolo — preferir `keyId` y caer a él es gratis.
    raw_id = data.get("keyId") or data.get("messageId")
    if not raw_id:
        return None
    state = state_from_provider(str(data.get("status") or ""))
    if state is None:
        return None
    return DeliveryReport(provider_message_id=str(raw_id), state=state)


class WebhookAck(BaseModel):
    """Always 200-shaped: a 4xx would make the bridge retry a message we already have."""

    status: str
    detail: str | None = None


def session_response(session: Any) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        branch_id=session.branch_id,
        provider_instance_ref=session.provider_instance_ref,
        status=session.status,
        phone_number=session.phone_number,
        last_seen_at=session.last_seen_at,
    )
