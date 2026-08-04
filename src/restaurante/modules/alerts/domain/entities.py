"""Entidades del módulo de alertas: la regla configurada y la alerta que dispara.

La decisión que sostiene el módulo entero es que **una alerta es una entidad con ciclo de
vida, no un mensaje**. Modelar "notificación" dejaría sin sitio dónde anotar que el tomate
sigue bajo, que ya lo dijimos y cuántas veces — y sin ese sitio no hay forma de insistir sin
convertirse en ruido.

                     ┌── tomar ──────► acknowledged
    armed ──▶ fired ─┼── silenciar ──► fired, callada        ──▶ resolved ──▶ armed
       ▲             └── resolverse ─────────────────────────────────┘   (pasado el colchón)
       │
       └─ mientras siga en `fired` y sin silenciar, el panel INSISTE cada
          `remind_every_minutes`, y WhatsApp cada 4 horas.

**Insistir sólo es sostenible porque callar cuesta un toque.** Las tres salidas son la parte
que hace defendible la repetición: sin la tercera —silenciar— la única forma de parar un aviso
sería tomarlo, o sea mentir diciendo que alguien se hizo cargo, y en una semana el registro de
quién atiende qué no valdría nada.

Todo lo que mantiene vivo el módulo —deduplicación, histéresis, quién la tomó, cuándo se avisó
por última vez, escalado— cuelga del estado, no del mensaje.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

# --- Estados ----------------------------------------------------------------
# `armed` no se guarda como fila: una alerta armada es la AUSENCIA de una alerta abierta para
# ese sujeto. Guardar el estado de reposo obligaría a crear una fila por cada ingrediente de
# cada sucursal antes de que pase nada.
ALERT_FIRED = "fired"
ALERT_ACKNOWLEDGED = "acknowledged"
ALERT_RESOLVED = "resolved"

ALERT_STATUSES = (ALERT_FIRED, ALERT_ACKNOWLEDGED, ALERT_RESOLVED)
#: Una alerta abierta es la que ocupa el sitio: mientras exista, esa condición no vuelve a
#: hablar. Es lo que hace que "avisar una vez" sea una constraint y no un `if ya_avisamos`.
OPEN_ALERT_STATUSES = (ALERT_FIRED, ALERT_ACKNOWLEDGED)

# --- Reglas conocidas -------------------------------------------------------
# Cada regla es código con parámetros configurables, no una condición que el dueño escriba.
# Un motor de reglas sobre texto libre es un producto en sí mismo y sería el riesgo
# equivocado para las tres primeras.
RULE_LOW_STOCK = "low_stock"
RULE_WHATSAPP_SESSION_DOWN = "whatsapp_session_down"
RULE_CASH_SESSION_LEFT_OPEN = "cash_session_left_open"
# El saldo del asistente a punto de agotarse. Es una regla más y no un aviso propio del
# asistente por una razón concreta: aquí ya está resuelto lo difícil —la histéresis—, así que
# el dueño se entera UNA vez y no en cada mensaje que le acerca al límite.
RULE_ASSISTANT_QUOTA = "assistant_quota"

KNOWN_RULE_KEYS = (
    RULE_LOW_STOCK,
    RULE_WHATSAPP_SESSION_DOWN,
    RULE_CASH_SESSION_LEFT_OPEN,
    RULE_ASSISTANT_QUOTA,
)

#: Colchón de recuperación por defecto, **en la unidad que declare cada regla**. Nunca cero: cero
#: es exactamente el fallo que la histéresis existe para impedir.
#:
#: Cada regla lo interpreta en lo suyo, y las unidades no son intercambiables:
#:   · stock bajo         → **porcentaje del mínimo del insumo** (10 = 10%)
#:   · caja abierta       → minutos
#:   · cuota del asistente→ puntos porcentuales
#:
#: El stock bajo es porcentual y no absoluto porque sus sujetos son insumos con unidades de medida
#: distintas entre sí: un colchón fijo significaría un 50% sobre 2 kg de camarón y un 0,2% sobre
#: 500 g de sal. Ver `LowStockEvaluator`.
DEFAULT_RECOVERY_BUFFER = 10
#: Cuánto se espera a que alguien la tome antes de gastar el PRIMER mensaje de WhatsApp.
#:
#: Cinco minutos, no treinta: en cinco minutos casi nadie ha mirado el panel, así que el primer
#: mensaje va a salir casi siempre. Es deliberado — el dueño quiere enterarse en el teléfono, no
#: en una pantalla que no está mirando— y sigue siendo por regla: quien prefiera que alguien mire
#: el panel antes, lo sube.
DEFAULT_ESCALATION_MINUTES = 5

#: Cada cuánto vuelve a salir un WhatsApp de una alerta que sigue sin tomar. Techo: 6 al día.
#:
#: **Constante del módulo y NO campo de la regla, a propósito.** El primer plazo dice cuándo
#: quiere enterarse el negocio y es asunto suyo; esto acota cuántos mensajes puede llegar a mandar
#: ese número en un día, y eso no es asunto de ninguna regla: quien paga un mensaje de más no es
#: el dueño, es el número, y bloquearlo deja mudo todo el WhatsApp del restaurante —pedidos
#: incluidos—. Un campo aquí es un campo para ponerlo en 15 minutos el día que algo urge, y ese
#: día es exactamente el que hay que impedir.
WHATSAPP_REESCALATION_HOURS = 4

#: Cada cuántos minutos vuelve a avisar el PANEL de una alerta abierta que nadie ha tocado.
#: `0` = no insistir, que es como se comportaba el módulo antes de que esto existiera.
DEFAULT_REMIND_MINUTES = 5


@dataclass
class AlertRule:
    """Una condición configurada para una sucursal.

    `threshold` es opcional y su significado lo pone cada regla: la de stock bajo no lo usa
    —reutiliza el `min_stock` que inventario ya lleva por (sucursal, ingrediente), porque dos
    umbrales para un mismo concepto divergen en un mes—, mientras que la de caja abierta lo
    lee como la hora a partir de la cual dejar la caja abierta es un problema.
    """

    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    rule_key: str
    is_enabled: bool = False
    threshold: float | None = None
    recovery_buffer: float = DEFAULT_RECOVERY_BUFFER
    #: Cada cuánto insiste el panel mientras nadie la toque. `0` = avisa una vez y calla.
    remind_every_minutes: int = DEFAULT_REMIND_MINUTES
    escalation_after_minutes: int = DEFAULT_ESCALATION_MINUTES
    escalate_to_whatsapp: bool = False
    id: uuid.UUID | None = None


@dataclass
class Alert:
    """Una instancia de una regla disparada, sobre un sujeto concreto.

    `subject_ref` es de quién habla la alerta: el ingrediente, la sesión de WhatsApp o la
    sesión de caja. Es texto y no una FK a propósito — apunta a tablas de tres módulos
    distintos, y una FK por regla convertiría añadir una regla en una migración.

    `subject_label` es cómo se llama eso para una persona. Se guarda porque deducirlo cada
    vez falla en el hueco de la histéresis y el aviso acaba diciendo un uuid.
    """

    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    rule_key: str
    subject_ref: str
    #: Cómo se llama el sujeto, congelado al disparar ("Azúcar"). `None` en alertas viejas.
    subject_label: str | None = None
    status: str = ALERT_FIRED
    fired_at: datetime | None = None
    acknowledged_at: datetime | None = None
    acknowledged_by: uuid.UUID | None = None
    resolved_at: datetime | None = None
    #: La ÚLTIMA vez que se escaló, no "si se escaló": el escalado ahora se repite cada 4 horas.
    last_escalated_at: datetime | None = None
    #: La última vez que se avisó de ella por el panel — el disparo cuenta como aviso.
    last_notified_at: datetime | None = None
    #: "Ya lo sé, cállate": deja de recordar SIN que nadie se haga cargo. La tercera salida.
    reminders_muted_at: datetime | None = None
    id: uuid.UUID | None = None

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_ALERT_STATUSES
