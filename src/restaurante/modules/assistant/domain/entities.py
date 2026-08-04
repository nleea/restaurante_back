"""Las entidades del asistente. Tres, y ninguna es la conversación de WhatsApp.

Lo que este módulo modela no es "hablar con un modelo" —eso es un adaptador— sino **lo que
hace que vender tokens no nos arruine**: quién tiene derecho a llamar, cuánto lleva gastado y
qué se le facturó por cada llamada.

Los tokens se compran al por mayor y se revenden (ver `docs/messaging/ROADMAP.md`), así que
el dinero que arde en un bucle es el NUESTRO. Por eso el contador no es un entero que baja:
es un libro mayor de sólo-añadir con dos capas —lo que nos costó el proveedor y lo que se le
facturó al tenant—, que es la única forma de contestar "¿qué tenant no es rentable?" antes de
que la respuesta sea evidente en la factura del proveedor.
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

# --- Quién llama -----------------------------------------------------------------------
# El tipo de llamador NO es un adorno: decide qué registro de herramientas se construye, y
# ese registro es toda la seguridad del módulo. Un cliente no tiene la herramienta de ventas
# porque no está en su registro, no porque el prompt le pida que no la use.
CALLER_CUSTOMER = "customer"
CALLER_EMPLOYEE = "employee"

#: Plan por defecto. El plan elige proveedor y modelo (decisión 3 del diseño): compramos al
#: por mayor, así que el modelo es una palanca de margen nuestra, no una preferencia del
#: tenant.
DEFAULT_PLAN = "basic"

#: El aviso al dueño sale al 80% de lo comprado. Se dispara sobre la maquinaria de
#: `alert-notifications`, que ya trae la histéresis: se avisa una vez, no en cada mensaje.
DEFAULT_WARNING_THRESHOLD_PERCENT = 80

#: Unidades que consume una llamada. El tenant se factura por MENSAJE (precio plano) y el
#: proveedor nos cobra por token: son dos monedas distintas y por eso el libro tiene dos
#: capas. Que hoy sea 1 no lo hace una constante inútil — es el sitio donde vivirá "el plan
#: premium cuenta doble" sin tocar el punto de estrangulamiento.
UNITS_PER_CALL = 1


@dataclass
class AssistantEntitlement:
    """Lo que un tenant compró. Sin fila, no hay asistente.

    `is_enabled` y `monthly_quota_units` son cosas distintas a propósito: apagar el asistente
    de un tenant que pagó no debe borrar lo que le queda, y comprar unidades no debe
    encenderlo por su cuenta.
    """

    tenant_id: uuid.UUID
    plan: str = DEFAULT_PLAN
    is_enabled: bool = False
    monthly_quota_units: int = 0
    # El ancla del periodo: el mes va de esta fecha a la misma fecha del mes siguiente, no
    # del 1 al 30. Es la suposición de trabajo hasta que exista un módulo de facturación
    # (ver "Open Questions" del diseño); vive como columna para poder cambiarla sin migrar.
    period_anchor: datetime | None = None
    warning_threshold_percent: int = DEFAULT_WARNING_THRESHOLD_PERCENT
    # Lo que se contesta cuando se acabó el saldo. Es un TEXTO, no un prompt: explicar que la
    # cuota se agotó llamando al modelo cuesta exactamente la llamada que no hay con qué
    # pagar.
    fallback_message: str = ""
    id: uuid.UUID | None = None


@dataclass
class UsageEntry:
    """Una llamada al modelo, ya ocurrida. El libro sólo crece.

    Las dos capas —`provider_cost` (lo que nos costó) y `billed_units` (lo que se le
    facturó)— son el instrumento para ver a un tenant cuyos clientes escriben ensayos: con
    una sola capa, ese tenant es indistinguible de uno rentable hasta que llega la factura.
    """

    tenant_id: uuid.UUID
    occurred_at: datetime
    caller_kind: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    provider_cost: Decimal
    billed_units: int
    conversation_ref: str | None = None
    id: uuid.UUID | None = None


@dataclass
class ConversationTurn:
    """Un turno de la charla, en NUESTRO vocabulario. Nada de LangChain llega hasta aquí."""

    role: str  # "user" | "assistant"
    text: str


@dataclass
class AssistantConversationState:
    """El hilo tal y como lo ve el asistente, que no es el hilo de WhatsApp.

    Se guarda aparte por dos motivos que no son estéticos:

    1. El chat de administración no tiene conversación de WhatsApp ninguna, y necesita
       historia igual. Un solo sitio para las dos vías evita escribir el flujo dos veces.
    2. El hilo de WhatsApp es el registro HUMANO: lleva saludos automáticos, comprobantes y
       lo que escribió el personal. Meterlo entero como contexto sería pagar tokens por
       nuestros propios avisos.

    `turns` se guarda ya recortado a la ventana: la historia es el principal motor del coste
    de entrada, así que lo que no cabe no se guarda en vez de guardarse y descartarse luego.
    """

    tenant_id: uuid.UUID
    conversation_ref: str
    caller_kind: str
    turns: list[ConversationTurn] = field(default_factory=list)
    branch_id: uuid.UUID | None = None
    last_turn_at: datetime | None = None
    id: uuid.UUID | None = None


# --- El periodo ------------------------------------------------------------------------


def _add_months(anchor: datetime, months: int) -> datetime:
    """El ancla desplazada `months` meses, recortando el día al último del mes destino.

    Se recorta contra el día del ANCLA, no contra el resultado anterior: un ancla del 31 pasa
    por el 28 de febrero y vuelve al 31 de marzo. Ir arrastrando el recorte convertiría
    cualquier ancla de fin de mes en un 28 para siempre, y el periodo de un tenant se movería
    solo.
    """
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return anchor.replace(year=year, month=month, day=day)


def period_bounds(anchor: datetime, now: datetime) -> tuple[datetime, datetime]:
    """`[inicio, fin)` del periodo de cuota que contiene a `now`.

    Mensual desde el ancla del tenant. Es un cálculo puro y vive en el dominio porque de él
    depende la única pregunta cara del camino caliente ("¿cuánto lleva gastado este mes?"):
    si el periodo se calculara en la consulta, cambiarlo sería tocar SQL.
    """
    months = (now.year - anchor.year) * 12 + (now.month - anchor.month)
    start = _add_months(anchor, months)
    if start > now:
        months -= 1
        start = _add_months(anchor, months)
    return start, _add_months(anchor, months + 1)
