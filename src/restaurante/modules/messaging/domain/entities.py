"""Framework-free domain entities of the messaging module.

Plain dataclasses mirroring the ORM models, with no SQLAlchemy dependency.
Required fields come first; optional fields (defaulting to ``None``) come last.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class WhatsAppSession:
    """A branch's paired WhatsApp number. Never carries provider credentials."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    provider_instance_ref: str
    status: str
    created_at: datetime
    updated_at: datetime
    phone_number: str | None = None
    last_seen_at: datetime | None = None


@dataclass
class WhatsAppContact:
    id: uuid.UUID
    tenant_id: uuid.UUID
    phone: str
    created_at: datetime
    updated_at: datetime
    name: str | None = None
    address: str | None = None


@dataclass
class WhatsAppConversation:
    id: uuid.UUID
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    whatsapp_contact_id: uuid.UUID
    status: str
    started_at: datetime
    employee_id: uuid.UUID | None = None
    closed_at: datetime | None = None
    store_token: str | None = None
    store_token_expires_at: datetime | None = None


@dataclass
class FaqEntry:
    """Una pregunta frecuente y las palabras con las que el cliente la hace.

    El `id` lo acuña quien la crea (la pantalla) y aquí sólo se conserva: es configuración dentro
    de un JSON, no una entidad con vida propia. Lo que el backend garantiza es que no se repita.

    El orden dentro de la lista ES la prioridad de coincidencia, así que esta clase no lleva
    campo de posición: la posición es el índice, y guardar las dos cosas sería tener dos verdades.
    """

    id: str
    name: str
    triggers: list[str] = field(default_factory=list)
    text: str = ""
    enabled: bool = False


@dataclass
class QuickReply:
    """Una frase que el negocio repite, guardada para que una PERSONA la inserte.

    No es una `FaqEntry` con menos campos: es otra cosa. Una FAQ la dispara el sistema leyendo el
    mensaje del cliente; esto lo mete un empleado en el compositor y lo manda él. De ahí que no
    lleve `enabled` (no dispara nunca, así que "apagada" sólo podría querer decir "bórrala") ni
    `triggers` (no se lee nada). Ver `domain/quick_reply.py`.

    Como en `FaqEntry`, el `id` lo acuña la pantalla y el orden de la lista es el índice.
    """

    id: str
    name: str
    text: str = ""


@dataclass
class AutoreplySettings:
    """Cómo responde solo un negocio. Sin fila → todo apagado (ver `DEFAULTS`).

    Salvedad, y es la única de esta clase: `quick_replies` **no responde sola**. Viaja aquí porque
    ésta es la fila de "cómo habla este negocio por WhatsApp" y ya se lee y se escribe entera, no
    porque sea un automatismo más.
    """

    tenant_id: uuid.UUID
    greeting_enabled: bool = False
    greeting_open_text: str = ""
    greeting_closed_text: str = ""
    # El saludo de quien tiene un pedido esperando pago. Vacío = usar el de abierto/cerrado.
    greeting_awaiting_payment_text: str = ""
    assistant_offer_enabled: bool = False
    idle_hours: int = 24
    token_lifetime_hours: int = 24
    # {"order_received": {"enabled": bool, "text": str}, …}
    status_mapping: dict[str, Any] = field(default_factory=dict)
    # `None` y `[]` NO significan lo mismo, y de esa distinción depende que una FAQ borrada no
    # resucite: `None` es "este tenant nunca las tocó" —se le ofrecen las sugeridas, apagadas— y
    # `[]` es "decidió que ninguna". Fusionar lo guardado sobre unos valores de fábrica, como se
    # hace con `status_mapping`, aquí sería un bug: ese mapeo tiene claves fijas y esta lista es
    # propiedad del dueño, que la reordena y borra de ella.
    faqs: list[FaqEntry] | None = None
    # Mismo `None` ≠ `[]` que `faqs`, por el mismo motivo (una borrada no puede resucitar) y con
    # una diferencia: aquí las sugeridas sólo se ofrecen en el EDITOR. El inbox recibe lo guardado
    # y nada más, así que `None` le llega como lista vacía.
    quick_replies: list[QuickReply] | None = None
    id: uuid.UUID | None = None


@dataclass
class WhatsAppMessage:
    id: uuid.UUID
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    whatsapp_conversation_id: uuid.UUID
    sender_type: str
    content: str
    delivery_state: str
    sent_at: datetime
    employee_id: uuid.UUID | None = None
    provider_message_id: str | None = None
    # `media_type` puede estar puesto SIN `media_url`: llegó un archivo y no se pudo traer. Es un
    # estado legítimo y es lo que el hilo tiene que saber contar.
    media_type: str | None = None
    media_mime: str | None = None
    media_url: str | None = None
