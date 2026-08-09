"""ORM models of the messaging module.

WhatsApp messaging tables: `whatsapp_sessions` (one paired number per branch),
`whatsapp_contacts` (people who write in), `whatsapp_conversations` (a contact's
thread on one branch) and `whatsapp_messages` (each message exchanged).

Contacts are tenant-scoped: one phone number is one person for the business, even
if they write to two branches. Everything else is branch-scoped — the customer
picks the branch by picking the number, so the receiving branch is known at the
webhook and must travel with the conversation and its messages.

The `employee_id` and `branch_id` foreign keys target tables owned by other
modules, so they are referenced by string.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import (
    Base,
    BranchScopedMixin,
    TenantScopedMixin,
    TimestampMixin,
)

# --- Value sets, kept as plain strings in the DB -----------------------------
# Session connection lifecycle. `banned` is terminal: the number must be replaced.
SESSION_CONNECTED = "connected"
SESSION_STATUSES = ("disconnected", "qr_pending", SESSION_CONNECTED, "banned")

# Conversation lifecycle.
#
# `new`     — nadie la ha tocado; es lo que dispara el saludo automático.
# `greeted` — ya se saludó. Existe para que el saludo salga UNA vez y no en cada mensaje.
# `bot`     — la atiende el asistente (llega con `assistant-core`; aquí sólo se reconoce).
# `human`   — la tomó un empleado.
# `closed`  — terminada, por un agente o por la ventana de inactividad.
CONVERSATION_STATUSES = ("new", "greeted", "bot", "human", "closed")
OPEN_CONVERSATION_STATUSES = ("new", "greeted", "bot", "human")

MESSAGE_SENDER_TYPES = ("contact", "employee", "system")

# Qué clase de estado se publica. El proveedor acepta además `video` y `audio`; el compositor de v1
# hace estos dos, y añadir los otros no cambia el modelo.
STATUS_TYPE_TEXT = "text"
STATUS_TYPE_IMAGE = "image"
STATUS_TYPES = (STATUS_TYPE_TEXT, STATUS_TYPE_IMAGE)

# Cómo acabó una franja vencida.
#
# `published`    — el puente aceptó la publicación. NO significa que alguien la haya visto: el
#                  proveedor no devuelve vistas y se come los fallos de las tandas siguientes.
# `failed`       — el puente la rechazó.
# `skipped_late` — venció fuera de la ventana de gracia y NO se publicó. Un estado caduca a las 24
#                  horas, así que sacar el menú del día por la tarde es peor que no sacarlo. Existe
#                  como fila y no como silencio para que el dueño pueda leer qué pasó.
PUBLICATION_PUBLISHED = "published"
PUBLICATION_FAILED = "failed"
PUBLICATION_SKIPPED_LATE = "skipped_late"
# `skipped_empty` — no quedó nadie a quien publicar después de las cuatro reducciones. No es
# `failed` (nada se rompió, y culpar al puente manda a mirar donde no está el problema) ni
# `published` (no salió). Existe por el mismo motivo que `skipped_late`: no publicar tiene que ser
# una fila que el dueño pueda leer, y aquí además la fila trae las cuatro exclusiones, que son
# exactamente la explicación de por qué no había nadie.
PUBLICATION_SKIPPED_EMPTY = "skipped_empty"
PUBLICATION_STATES = (
    PUBLICATION_PUBLISHED,
    PUBLICATION_FAILED,
    PUBLICATION_SKIPPED_LATE,
    PUBLICATION_SKIPPED_EMPTY,
)

# Tipos de emisión automática. Son las claves de deduplicación: cada uno se envía una vez.
EMISSION_GREETING = "greeting"
EMISSION_STATUS = "status"
# Una respuesta por (conversación, FAQ): preguntar dos veces lo mismo en un hilo recibe una
# contestación. Con cuatro FAQs, el techo son cuatro automáticos por conversación — el mismo
# orden de magnitud que el mapeo de estados por pedido.
EMISSION_FAQ = "faq"
# Una emisión por solicitud de pago, no por pedido: re-cotizar un domicilio acuña una solicitud
# nueva y esa SÍ debe salir. El id de la solicitud viaja en `detail` y es lo que las separa.
EMISSION_PAYMENT_REQUEST = "payment_request"
# Una publicación por (estado, fecha local, minuto). La clase es `status_post` y **no** `status`
# porque `status` ya es de los avisos de estado de un pedido, justo arriba. Las dos nunca chocarían
# de verdad —un id de pedido no es un id de estado— pero convivirían en esta columna con la misma
# cara, y esta columna es donde se audita a mano por qué algo salió dos veces.
#
# No usa NINGUNA de las columnas con FK: una publicación de estado no cuelga de una conversación
# ni de un pedido. Va entera en `detail`, que es lo que compone
# `domain/status_schedule.emission_detail`.
EMISSION_STATUS_POST = "status_post"


def emission_key(
    kind: str,
    *,
    conversation_id: uuid.UUID | None = None,
    order_id: uuid.UUID | None = None,
    customer_state: str | None = None,
    detail: str | None = None,
) -> str:
    """La clave textual de una emisión: `greeting:<conv>` / `status:<pedido>:<estado>` /
    `faq:<conversación>:<id de la FAQ>`.

    Se compone aquí y no en el repositorio para que la forma de la clave sea un hecho de
    la tabla. Cambiarla es cambiar qué cuenta como "el mismo mensaje".

    `detail` es texto libre que forma parte de la clave y **no** tiene columna propia: a
    diferencia de la conversación y el pedido no apunta a ninguna fila, así que una columna
    sólo repetiría un trozo de la clave sin una FK que la sostenga. Para auditar, el id de la
    FAQ se lee del propio `dedupe_key`.
    """
    parts = [
        kind,
        str(conversation_id or ""),
        str(order_id or ""),
        customer_state or "",
        detail or "",
    ]
    return ":".join(part for part in parts if part)

# Outbound reconciliation. Inbound messages are born `sent`: they already arrived,
# there is nothing left to reconcile.
# Los estados de un mensaje saliente. `pending → sent` los pone el envío; `delivered → read` los
# ponen los acuses del proveedor, y sólo suben (ver `domain/delivery.py`). `failed` está fuera de
# esa escala: es el otro final, y un mensaje así nunca llegó a tener id de proveedor.
#
# La columna es `String(20)` sin CHECK ni enum, así que esta tupla es la única declaración de qué
# valores existen. Es documentación con nombre, no una constraint.
MESSAGE_DELIVERY_STATES = ("pending", "sent", "delivered", "read", "failed")


class WhatsAppSessionModel(Base, BranchScopedMixin, TimestampMixin):
    """One WhatsApp number per branch.

    Holds only the provider's instance reference, the connection status and the
    paired number — never authentication material. The bridge owns the auth state
    and must persist it itself; storing it here would mean owning a secret we can
    neither rotate nor use.
    """

    __tablename__ = "whatsapp_sessions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "branch_id", name="uq_whatsapp_sessions_tenant_branch"
        ),
        UniqueConstraint(
            "tenant_id",
            "provider_instance_ref",
            name="uq_whatsapp_sessions_tenant_instance_ref",
        ),
        # The webhook resolves a session by instance ref before it knows the tenant,
        # so that lookup needs its own index.
        Index("ix_whatsapp_sessions_provider_instance_ref", "provider_instance_ref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider_instance_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="disconnected", nullable=False
    )
    phone_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WhatsAppContactModel(Base, TenantScopedMixin, TimestampMixin):
    """A person who wrote in. Tenant-scoped: one phone is one person per business."""

    __tablename__ = "whatsapp_contacts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "phone", name="uq_whatsapp_contacts_tenant_phone"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # "No me manden más estados". Vive en el CONTACTO y no en la conversación, aunque la audiencia
    # de un estado sea por sede: la petición se le hace al negocio, y obligar a la persona a
    # repetirla en cada sucursal es cómo se consigue que bloquee el número en vez de volver a
    # pedirlo.
    #
    # No afecta a nada más: un contacto marcado sigue siendo alcanzable para responderle, su hilo
    # sigue en la bandeja y su historial no se toca. Es lo que lo separa de borrar el contacto, que
    # era la única forma de sacar a alguien de la lista antes de que existiera esta columna.
    status_opt_out: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )


class WhatsAppConversationModel(Base, BranchScopedMixin):
    """A contact's thread on one branch. The same phone on two branches is two threads."""

    __tablename__ = "whatsapp_conversations"
    __table_args__ = (
        # The inbox lists open conversations of one branch, newest first.
        Index("ix_whatsapp_conversations_branch_status", "branch_id", "status"),
        # El token es la credencial del enlace: dos conversaciones no pueden compartirlo.
        # Los NULL no chocan entre sí, así que las conversaciones sin enlace conviven.
        UniqueConstraint(
            "tenant_id",
            "store_token",
            name="uq_whatsapp_conversations_tenant_store_token",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    whatsapp_contact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Capability URL para el enlace a la carta. Opaco, aleatorio, con vencimiento y
    # REUTILIZABLE mientras viva: el cliente reabre el enlace una hora después para pedir de
    # nuevo, y un token de un solo uso se leería como que el sistema está roto.
    #
    # Resuelve a un CONTACTO, nunca a un pedido: un enlace filtrado no puede leer el
    # historial de nadie. Lo peor que puede pasar es un comprobante entregado a quien no era,
    # y por eso vence.
    store_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    store_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WhatsAppAutoreplySettingsModel(Base, TenantScopedMixin, TimestampMixin):
    """Cómo responde solo este negocio. Una fila por tenant, o ninguna (todo apagado).

    El texto del saludo es de TENANT, no de sucursal: mantener tres saludos para tres sedes
    del mismo restaurante es peor producto que un saludo que sabe en qué sede está. La sede
    aporta sus horarios y su enlace por interpolación.
    """

    __tablename__ = "whatsapp_autoreply_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_whatsapp_autoreply_settings_tenant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Apagado por defecto: instalar este change no puede cambiar el comportamiento de nadie.
    greeting_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    greeting_open_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    greeting_closed_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Tercera variante: el contacto tiene un pedido prepago sin pagar. Se elige por el ESTADO del
    # pedido, nunca por lo que el cliente escribió — el saludo sigue sin leer el texto, que es la
    # regla #1 del módulo. Vacía cae a la de abierto/cerrado; nunca a silencio.
    greeting_awaiting_payment_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    # El saludo NUNCA debe ofrecer algo que no vaya a responder: mientras el tenant no tenga
    # el asistente, esta línea se omite y "quiero hablar con alguien" va al inbox humano.
    assistant_offer_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    idle_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    token_lifetime_hours: Mapped[int] = mapped_column(
        Integer, default=24, nullable=False
    )
    # Qué transiciones internas le hablan al cliente y con qué texto:
    # `{"order_received": {"enabled": true, "text": "..."}, …}`.
    # JSON y no tablas porque es configuración que se lee entera y se escribe entera.
    status_mapping: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    # Las FAQs por palabra clave, en orden — el orden ES la prioridad de coincidencia:
    # `[{"id": "...", "name": "Ubicación", "enabled": true, "triggers": [...], "text": "..."}, …]`
    #
    # **Nullable a propósito, y `NULL` no es `[]`.** `NULL` = este tenant nunca las tocó, así que
    # se le ofrecen las sugeridas (apagadas); `[]` = decidió que ninguna. Sin esa distinción no
    # hay forma de distinguir "no las he configurado" de "las borré todas", y una FAQ borrada
    # resucitaría en la siguiente lectura — el mismo bug que el `armed` sin fila de las alertas.
    #
    # No se fusiona con unos valores de fábrica como `status_mapping`: ese mapeo tiene claves
    # fijas (seis transiciones) y esto es una lista que el dueño reordena y de la que borra.
    faqs: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True, default=None)
    # Las respuestas rápidas, en orden: `[{"id": "...", "name": "Gracias", "text": "..."}, …]`.
    #
    # **Esto NO contesta solo, pese a vivir en una tabla que se llama `autoreply`.** Es texto que
    # un empleado inserta en el compositor y manda él. Vive aquí porque ésta es la fila de "cómo
    # habla este negocio por WhatsApp", ya es una por tenant y ya se lee y se escribe entera; una
    # tabla propia habría costado migración, modelo, repositorio y router para comprar cero
    # consultas nuevas. Si algún día alguien busca dónde se disparan, la respuesta es que en
    # ningún sitio: no aparecen en el pipeline de entrada y ése es el invariante del change.
    #
    # Mismo `NULL` ≠ `[]` que `faqs` y por el mismo motivo —una borrada no puede resucitar—, con
    # una diferencia: las sugeridas se ofrecen SÓLO en el editor. El inbox recibe lo guardado, así
    # que para él `NULL` es lista vacía; enseñarle al mesero plantillas que el dueño nunca aprobó
    # sería poner palabras en boca del negocio.
    quick_replies: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, default=None
    )


class WhatsAppOutboundEmissionModel(Base, BranchScopedMixin):
    """La marca de "esto ya se envió". Su única razón de existir es la unicidad.

    Un `if last_sent_at is None` es una carrera entre dos workers: ambos leen vacío y ambos
    envían. Aquí la unicidad la impone la base de datos: se intenta insertar, y sólo quien
    gana la inserción envía.

    Dos clases de emisión conviven en la misma tabla:
      greeting:<conversación>          → un saludo por conversación
      status:<pedido>:<estado>         → un aviso por estado y pedido

    Y la clave es UNA columna de texto, `dedupe_key`, no la tupla de columnas.
    Un `UNIQUE(tenant, kind, conversation_id, order_id, customer_state)` parece más
    expresivo y es justo lo que NO funciona: en SQL dos NULL no son iguales, así que
    `('status', NULL, pedido, 'on_the_way')` es único consigo mismo y el aviso sale en
    cada rebote. Las columnas siguen ahí, con sus FK, para poder auditar y para que
    borrar un pedido se lleve sus emisiones.
    """

    __tablename__ = "whatsapp_outbound_emissions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "dedupe_key", name="uq_whatsapp_emissions_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(120), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("whatsapp_conversations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("orders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    customer_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    emitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WhatsAppMessageModel(Base, BranchScopedMixin):
    __tablename__ = "whatsapp_messages"
    __table_args__ = (
        # Idempotency for the bridge's redeliveries. NULLs are distinct in Postgres,
        # so outbound messages awaiting a provider id do not collide with each other.
        UniqueConstraint(
            "tenant_id",
            "provider_message_id",
            name="uq_whatsapp_messages_tenant_provider_id",
        ),
        Index("ix_whatsapp_messages_conversation_sent_at", "whatsapp_conversation_id", "sent_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    whatsapp_conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("whatsapp_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Null until the provider acknowledges an outbound send; always set for inbound.
    provider_message_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    # La dirección del proveedor, TAL CUAL llegó. Hace falta para pedirle después el archivo de
    # este mensaje: el proveedor exige la clave entera (`{id, remoteJid, fromMe}`), no sólo el id.
    # Se guarda en vez de reconstruirla del teléfono porque los JID de WhatsApp tienen más de una
    # forma (`@s.whatsapp.net`, `@lid`) y esa reconstrucción ya fue una de las trampas conocidas.
    provider_remote_jid: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Qué clase de archivo traía el mensaje (`image` / `document`), **aunque no se haya guardado**.
    # Es lo que permite decir "llegó una imagen" sin tener el archivo, y lo que hace legible el
    # hueco cuando el puente no lo devolvió.
    media_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    media_mime: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # URL pública y opaca en R2. Nula cuando el archivo no se guardó — por tipo, por tamaño, o
    # porque el puente no lo devolvió.
    media_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    delivery_state: Mapped[str] = mapped_column(
        String(20), default="sent", nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WhatsAppStatusModel(Base, BranchScopedMixin, TimestampMixin):
    """Un estado de WhatsApp que el negocio publica solo, a una hora.

    Es lo PRIMERO que este módulo emite sin que nadie pregunte, y no rompe la invariante de no
    escribir primero porque un estado no aterriza en ninguna conversación: aparece en "Novedades",
    lo abre quien quiere, no espera respuesta y caduca solo a las 24 horas.

    Por sede y no por tenant, porque la sesión de WhatsApp es por sede: el estado se publica DESDE
    un número, y quien no tiene ESE número guardado no lo ve nunca.

    **No hay campo `kind`.** Las franjas de `whatsapp_status_slots` son el horario, y "todos los
    días" son siete filas. Un `kind` sería un segundo sitio decidiendo el mismo hecho, capaz de
    contradecir a sus propias filas. Tampoco hay bandera de "sólo si estamos abiertos", por lo
    mismo: el selector de días ya es la respuesta.
    """

    __tablename__ = "whatsapp_statuses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # `text` | `image`. El proveedor acepta además `video` y `audio`; el compositor de v1 no.
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    # El texto de la tarjeta, o el pie cuando el tipo es imagen y `caption` va vacío.
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Los DOS campos que el proveedor exige para un estado de texto o devuelve 400. No son
    # decoración: son la razón de que un estado se "componga" en vez de escribirse, y de que se
    # validen AL GUARDAR — descubrir el 400 a las once, en el worker, es enterarse por un teléfono
    # vacío. Nulos sólo cuando el tipo es imagen.
    bg_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    font: Mapped[int | None] = mapped_column(Integer, nullable=True)
    caption: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # URL pública y opaca en R2, por el mismo camino presignado que el comprobante y el multimedia
    # entrante. Al proveedor le va la URL, nunca base64.
    media_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )


class WhatsAppStatusSlotModel(Base, BranchScopedMixin):
    """Una ocasión en la que un estado se publica: un día de la semana O una fecha, más la hora.

    `minute` son minutos desde medianoche en hora **local de la sede**, exactamente como
    `operating_hours` — de donde sale toda la forma de esta tabla.

    El CHECK de exclusión mutua vive en la BASE y no sólo en el dominio a propósito: una inserción
    de un script de datos no pasa por `validate_slots`, y una franja con día y fecha a la vez es una
    ambigüedad que el barrido resolvería en silencio.

    Lleva tenant y sede propios aunque cuelgue de un estado que ya los tiene, y aunque el CASCADE la
    borre con él. Es el mismo trato que `whatsapp_messages`, que también los repite sobre una
    conversación que ya los lleva: el filtro automático de tenancy es defensa en profundidad y sólo
    protege lo que hereda el mixin, así que una fila de datos de un tenant sin él queda fuera del
    único mecanismo que ataja una consulta a la que se le olvidó el join.

    **Las filas se reescriben enteras al guardar** (borrar todo + reinsertar), como
    `operating_hours`. Eso es lo correcto para un conjunto que se edita como un todo, y es
    exactamente lo que obliga a que la clave de emisión NO lleve el id de esta fila — ver
    `domain/status_schedule.emission_detail`.
    """

    __tablename__ = "whatsapp_status_slots"
    __table_args__ = (
        CheckConstraint(
            "(weekday IS NULL) <> (on_date IS NULL)",
            name="ck_whatsapp_status_slots_weekday_xor_date",
        ),
        Index("ix_whatsapp_status_slots_status", "whatsapp_status_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    whatsapp_status_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("whatsapp_statuses.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 0=lunes … 6=domingo. Mismo convenio que `hours.py`, `operating_hours` y `datetime.weekday()`.
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    on_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    minute: Mapped[int] = mapped_column(Integer, nullable=False)


class WhatsAppStatusPublicationModel(Base, BranchScopedMixin):
    """Qué pasó cuando venció una franja. La única respuesta a "¿se publicó?".

    Existe porque no hay otra forma de saberlo: el proveedor no devuelve vistas, y devuelve 201
    aunque la mitad de los lotes se hayan caído dentro de un `Promise.allSettled`. Así que esta
    tabla no guarda lo que llegó —eso es incognoscible— sino **lo que se intentó**.

    De ahí el nombre de `addressed_count`, y de ahí que sea el nombre y no un comentario: la
    tentación de leerlo como "le llegó a 200" es la razón por la que la pantalla podría acabar
    diciendo "visto por 200", que es mentira. Se dirigió a 200. Nada más.

    Las cuatro columnas de exclusión no se suman en una: el spec exige poder decir *por qué* la
    audiencia bajó de 340 a 200, y un total no lo dice. Un `excluded_by_cap` mayor que cero es lo
    único que distingue "esto llegó a todos los que podía" de "esto se truncó".
    """

    __tablename__ = "whatsapp_status_publications"
    __table_args__ = (
        Index(
            "ix_whatsapp_status_publications_status_day",
            "whatsapp_status_id",
            "fired_for_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    whatsapp_status_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("whatsapp_statuses.id", ondelete="CASCADE"),
        nullable=False,
    )
    # La fecha LOCAL y el minuto de la franja que venció — los dos trozos de la clave de emisión.
    # Se guardan como columnas además de dentro de la clave porque esta tabla se lee por pantalla
    # ("11:00 · publicado") y `created_at` no sirve para eso: un omitido se registra tarde.
    fired_for_date: Mapped[date] = mapped_column(Date, nullable=False)
    minute: Mapped[int] = mapped_column(Integer, nullable=False)
    # `published` | `failed` | `skipped_late`. Ver `PUBLICATION_STATES`.
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    # A cuántos se DIRIGIÓ. No a cuántos llegó — eso no se puede saber.
    addressed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    excluded_no_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    excluded_opted_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    excluded_inactive: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    excluded_by_cap: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Minutos de retraso respecto a la franja. Es lo que hace legible un `skipped_late`: sin esto,
    # "omitido" es un silencio con fila.
    late_by_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # El id que devolvió el proveedor para la PRIMERA tanda. Es lo único con lo que correlacionar
    # algo después; no dice nada de las tandas siguientes.
    provider_message_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
