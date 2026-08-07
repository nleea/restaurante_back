"""Ports (interfaces) of the messaging module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from restaurante.modules.messaging.domain.entities import (
    AutoreplySettings,
    WhatsAppContact,
    WhatsAppConversation,
    WhatsAppMessage,
    WhatsAppSession,
)


@dataclass
class ConversationSummary:
    """One row of the inbox list: the conversation plus what it takes to triage it.

    The preview and the unread flag are derived from the last message rather than
    stored, so there is one source of truth for "what was said last".
    """

    conversation: WhatsAppConversation
    contact: WhatsAppContact
    last_message_at: datetime | None
    last_message_preview: str | None
    last_message_sender_type: str | None
    message_count: int
    # Resolved server-side: an agent with only `messaging.read` cannot query the staff
    # directory, so "held by whom" has to arrive already answered.
    holder_name: str | None = None

    @property
    def awaiting_reply(self) -> bool:
        """True when the contact spoke last — the inbox's unread signal."""
        return self.last_message_sender_type == "contact"


@dataclass
class OrderContext:
    """Lo mínimo que hace falta para redactar y dirigir un aviso de estado.

    Se resuelve de una sola pasada porque el aviso es un camino caliente: llega detrás
    de una transición que ya ocurrió y no puede pagar cuatro viajes a la base.

    `contact_id` es None cuando el pedido no lo hizo nadie que nos escribiera por
    WhatsApp (un pedido de mostrador, por ejemplo). Ese pedido no habla con nadie.
    """

    order_id: uuid.UUID
    branch_id: uuid.UUID
    total: Decimal
    contact_id: uuid.UUID | None = None
    phone: str | None = None


@dataclass(frozen=True)
class BusinessIdentity:
    """Cómo se llama y dónde está el negocio, tal y como lo dejó el Perfil del negocio.

    Es la respuesta a un fallo concreto: el saludo decía "Bienvenido a Main Branch" —el
    nombre que la semilla le puso a la sucursal— mientras el dueño ya había rellenado el
    perfil con el nombre de verdad de su restaurante. El dato existía y el mensaje no lo
    miraba.

    `business_name` es del tenant (uno por negocio); el resto es de la sucursal que recibió
    el mensaje, porque la dirección y el teléfono que le sirven al cliente son los de la sede
    a la que escribió, no los de la central.
    """

    business_name: str
    branch_name: str
    branch_address: str | None = None
    branch_phone: str | None = None


@dataclass
class OrderLineSummary:
    """Una línea del pedido tal y como se le cuenta al cliente por el chat."""

    name: str
    quantity: int
    line_subtotal: Decimal


@dataclass(frozen=True)
class UnsettledOrder:
    """Un pedido de este contacto al que todavía le falta plata.

    Es lo que la bandeja ofrece al usar una imagen como comprobante: sin el saldo, quien pulsa
    tiene que ir a buscar cuánto se debía, y adivinarlo es justo lo que no se le puede pedir.
    """

    order_id: uuid.UUID
    branch_id: uuid.UUID
    total: Decimal
    paid: Decimal

    @property
    def balance(self) -> Decimal:
        return self.total - self.paid


class MessagingRepository(Protocol):
    async def order_lines(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[OrderLineSummary]:
        """Qué compró, para poder contárselo. Sin ítems cancelados: ya no los tiene."""
        ...

    # --- Sessions ------------------------------------------------------------
    async def get_session(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> WhatsAppSession | None: ...

    async def get_session_for_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> WhatsAppSession | None: ...

    async def find_session_by_instance_ref(
        self, provider_instance_ref: str
    ) -> WhatsAppSession | None:
        """Tenant-less on purpose: the webhook resolves the tenant *from* the session."""
        ...

    async def list_sessions(self, tenant_id: uuid.UUID) -> list[WhatsAppSession]: ...

    async def create_session(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        provider_instance_ref: str,
    ) -> WhatsAppSession: ...

    async def update_session(
        self,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        changes: dict[str, object],
    ) -> WhatsAppSession | None: ...

    async def branch_exists(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool: ...

    # --- Contacts ------------------------------------------------------------
    async def find_or_create_contact(
        self, tenant_id: uuid.UUID, phone: str, name: str | None = None
    ) -> WhatsAppContact: ...

    async def get_contact(
        self, tenant_id: uuid.UUID, contact_id: uuid.UUID
    ) -> WhatsAppContact | None: ...

    async def find_contact_by_phone(
        self, tenant_id: uuid.UUID, phone: str
    ) -> WhatsAppContact | None: ...

    async def is_reachable(self, tenant_id: uuid.UUID, phone: str) -> bool:
        """True only when a contact exists for the phone AND has ≥1 inbound message.

        The single predicate behind the outbound invariant.
        """
        ...

    # --- Conversations -------------------------------------------------------
    async def get_conversation(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> WhatsAppConversation | None: ...

    async def find_open_conversation(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, contact_id: uuid.UUID
    ) -> WhatsAppConversation | None:
        """The most recently active open thread. Staleness is the service's call."""
        ...

    async def find_latest_conversation(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, contact_id: uuid.UUID
    ) -> WhatsAppConversation | None:
        """The most recent thread, open or closed. For messages a closed thread must not eat."""
        ...

    async def last_activity_at(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> datetime | None: ...

    async def create_conversation(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, contact_id: uuid.UUID
    ) -> WhatsAppConversation: ...

    async def list_conversations(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        include_closed: bool = False,
    ) -> list[ConversationSummary]: ...

    async def update_conversation_status(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID, status: str
    ) -> None:
        """Mueve el estado sin tocar nada más (p. ej. `new` → `greeted`)."""
        ...

    async def close_conversation(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> WhatsAppConversation | None: ...

    async def claim_conversation(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        employee_id: uuid.UUID,
    ) -> WhatsAppConversation | None:
        """Conditional UPDATE `WHERE employee_id IS NULL`.

        Returns None when another employee already holds it — the caller reads the
        current holder to name them.
        """
        ...

    async def employee_id_for_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, branch_id: uuid.UUID
    ) -> uuid.UUID | None:
        """Cross-module read (employees): who is acting, on which branch."""
        ...

    async def employee_display_name(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> str | None:
        """Cross-module read (employees → users) so the inbox can name a holder."""
        ...

    # --- Autoreply: ajustes, emisiones, token --------------------------------
    async def get_autoreply_settings(
        self, tenant_id: uuid.UUID
    ) -> AutoreplySettings | None:
        """La configuración del tenant, o None si nunca la tocó (todo apagado)."""
        ...

    async def upsert_autoreply_settings(
        self, settings: AutoreplySettings
    ) -> AutoreplySettings: ...

    async def try_claim_emission(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        kind: str,
        conversation_id: uuid.UUID | None = None,
        order_id: uuid.UUID | None = None,
        customer_state: str | None = None,
        detail: str | None = None,
    ) -> bool:
        """True sólo para quien GANA la inserción — y sólo ese envía.

        Es insert-or-ignore sobre la constraint de unicidad, no un `if last_sent_at`:
        dos workers leyendo "todavía nadie envió" mandan dos mensajes al cliente.
        """
        ...

    async def set_store_token(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        token: str,
        expires_at: datetime,
    ) -> None: ...

    async def find_conversation_by_token(
        self, token: str
    ) -> WhatsAppConversation | None:
        """Sin tenant: el token ES la credencial, igual que el instance_ref del webhook."""
        ...

    async def unsettled_orders_for_contact(
        self, tenant_id: uuid.UUID, contact_id: uuid.UUID, *, since: datetime
    ) -> list[UnsettledOrder]:
        """Los pedidos de ESTE contacto a los que les falta plata, del más nuevo al más viejo.

        Sirve para dos cosas y por eso devuelve la lista: ofrecerlos en la bandeja, y comprobar
        que el pedido que llega en la petición es de ese contacto — un id de otro cliente es un
        salto disfrazado de comodidad.
        """
        ...

    async def orders_using_proofs(
        self, tenant_id: uuid.UUID, urls: list[str]
    ) -> dict[str, uuid.UUID]:
        """De estos archivos, cuáles ya son comprobante de un pedido: `url → pedido`."""
        ...

    async def find_message(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID, message_id: uuid.UUID
    ) -> WhatsAppMessage | None:
        """Un mensaje concreto de una conversación concreta. `None` si no es de ahí."""
        ...

    async def unsettled_prepaid_order(
        self, tenant_id: uuid.UUID, contact_id: uuid.UUID, *, since: datetime
    ) -> OrderContext | None:
        """El pedido prepago de este contacto que todavía debe plata, si hay uno.

        Lo usa la tercera variante del saludo. Se elige por el ESTADO del pedido, nunca por lo
        que el cliente escribió.
        """
        ...

    async def has_live_order(
        self, tenant_id: uuid.UUID, contact_id: uuid.UUID, *, since: datetime
    ) -> bool:
        """¿Tiene este contacto un pedido sin terminar creado después de `since`?

        Lo pregunta el gate de las FAQs: quien está a mitad de un pedido no está haciendo una
        pregunta general, y contestarle un folleto es el peor resultado posible.
        """
        ...

    async def order_context(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderContext | None:
        """Lectura entre módulos (`orders` → contacto): a quién le habla este pedido.

        Primero por `orders.whatsapp_contact_id` (el pedido llegó por el enlace del
        saludo, así que sabemos exactamente quién es). Si no, por el teléfono del
        cliente: el mismo número que nos escribió es la misma persona.
        """
        ...

    async def tenant_slug(self, tenant_id: uuid.UUID) -> str | None:
        """El subdominio del tenant. Es lo que hace que el enlace lleve a SU carta."""
        ...

    async def branch_code(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> str | None: ...

    async def branch_name(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> str | None: ...

    async def business_identity(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> BusinessIdentity:
        """Quién es el negocio, según el Perfil del negocio.

        Existe porque `branch_name` a secas no basta para redactar un saludo: la sucursal se
        llama "Main Branch" hasta que alguien la renombra, mientras que el nombre del negocio
        es lo primero que el dueño rellena. Un saludo que dice "Bienvenido a Main Branch"
        cuando el perfil dice "Sabor Costeño" es la pantalla de ajustes ignorando el dato que
        el propio producto pidió.
        """
        ...

    async def branch_hours(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[tuple[int, int, int]]:
        """Ventanas horarias como (weekday, open_minute, close_minute)."""
        ...

    # --- Messages ------------------------------------------------------------
    async def list_messages(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> list[WhatsAppMessage]: ...

    async def add_message(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        sender_type: str,
        content: str,
        employee_id: uuid.UUID | None = None,
        provider_message_id: str | None = None,
        delivery_state: str = "sent",
        media_type: str | None = None,
        media_mime: str | None = None,
    ) -> WhatsAppMessage: ...

    async def attach_media(
        self, tenant_id: uuid.UUID, message_id: uuid.UUID, media_url: str
    ) -> None:
        """Pega la URL del archivo a un mensaje ya guardado.

        Separado del insert a propósito: el mensaje se guarda primero, así que un fallo bajando el
        archivo cuesta el archivo y nunca el mensaje.
        """
        ...

    async def add_inbound_message_once(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        content: str,
        provider_message_id: str,
        provider_remote_jid: str | None = None,
        media_type: str | None = None,
        media_mime: str | None = None,
    ) -> WhatsAppMessage | None:
        """Insert-or-ignore on `(tenant_id, provider_message_id)`.

        Returns None when the message was already stored, which is how the webhook
        tells a redelivery from a genuinely new message without racing.
        """
        ...

    async def mark_delivery(
        self,
        tenant_id: uuid.UUID,
        message_id: uuid.UUID,
        *,
        delivery_state: str,
        provider_message_id: str | None = None,
    ) -> WhatsAppMessage | None: ...

    async def apply_delivery_report(
        self,
        tenant_id: uuid.UUID,
        provider_message_id: str,
        state: str,
    ) -> bool:
        """Sube el acuse de un saliente. `True` sólo si el estado cambió de verdad."""
        ...


class WhatsAppGateway(Protocol):
    """La superficie hacia el puente. Un verbo de salida y uno de lectura.

    Salida: texto y archivos. Ni plantillas ni botones — el puente es no oficial y va a
    cambiarse, y un puerto estrecho hace que eso sea un adaptador barato. Mandar un archivo no
    ensancha el puerto de verdad: es el mismo verbo con otro cuerpo, y los dos pasan por el guard.

    Lectura: `fetch_media` existe porque el archivo de un mensaje entrante no viene en el
    webhook, hay que pedirlo. No rompe la propiedad de arriba —seguimos sin poder mandar
    un archivo— y la API oficial de Meta también sabe descargar, así que sustituir el
    puente sigue siendo escribir un adaptador.
    """

    async def send_text(
        self,
        session: WhatsAppSession,
        to_phone: str,
        body: str,
    ) -> str:
        """Send `body` to `to_phone`, returning the provider's message id.

        Raises `ContactNotReachableError` when the recipient never wrote first, and
        `MessageDeliveryError` when the bridge rejects or is unreachable.
        """
        ...

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
        """Manda un archivo y devuelve el id del proveedor.

        Es SALIDA, así que pasa por el guard igual que `send_text`: escribirle un archivo a quien
        no nos escribió primero es exactamente lo que hace que baneen un número.

        El puerto sigue sin saber de plantillas ni de botones. Un archivo no es una plantilla: es
        el mismo verbo de siempre con otro cuerpo, y cualquier puente —incluida la API oficial—
        sabe hacerlo.
        """
        ...

    async def fetch_media(
        self,
        session: WhatsAppSession,
        provider_message_id: str,
        remote_jid: str,
        *,
        from_me: bool = False,
    ) -> bytes:
        """Los bytes del archivo de un mensaje entrante ya recibido.

        Pide la **clave** del mensaje y no sólo su id porque el proveedor la exige entera
        (`{id, remoteJid, fromMe}`). El `remoteJid` se guarda tal y como llegó en vez de
        reconstruirlo del teléfono: los JID de WhatsApp tienen más de una forma
        (`@s.whatsapp.net`, `@lid`) y esa reconstrucción ya fue una de las trampas de la
        integración original.

        Levanta `MediaUnavailableError` cuando el puente no lo devuelve — que casi nunca es
        la red, sino que el puente no conserva los mensajes.
        """
        ...

    async def start_pairing(
        self, session: WhatsAppSession, webhook_url: str, webhook_secret: str
    ) -> str | None:
        """Prepara la instancia para escanear y devuelve el QR (data-URI), o None si ya
        está conectada.

        Registrar el webhook es parte de emparejar, no un paso aparte: un número emparejado
        sin webhook recibe mensajes que no llegan a ninguna parte.
        """
        ...
