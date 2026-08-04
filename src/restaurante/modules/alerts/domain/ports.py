"""Puertos del módulo de alertas.

La flecha de dependencia sale de `alerts` y nunca entra. Dos consecuencias que importan:

- `NotificationChannel` es un puerto, así que alertas **nunca importa messaging**. El módulo
  es enviable y probable antes, durante o completamente sin WhatsApp.
- `AlertRuleEvaluator` es un protocolo, así que `assistant-core` podrá registrar la regla de
  cuota más adelante sin tocar nada de aquí.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from restaurante.modules.alerts.domain.entities import Alert, AlertRule


@dataclass(frozen=True)
class Subject:
    """De qué habla una evaluación: la referencia y cómo llamarla en un mensaje.

    El `label` viaja con el sujeto en vez de resolverse al notificar porque quien sabe que
    `subject_ref` es un id de ingrediente es el evaluador, y hacer que el canal lo averigüe
    obligaría al canal a conocer inventario.
    """

    ref: str
    label: str
    #: Datos para redactar el aviso ("quedan 2 kg de 10"). Sin estructura fija a propósito:
    #: cada regla dice lo suyo y el canal sólo los interpola.
    detail: str = ""


@dataclass
class Evaluation:
    """El resultado de mirar una regla: qué debe hablar y qué ya se recuperó.

    Las dos listas son independientes y ambas necesarias. Sin `cleared` una alerta se queda
    abierta para siempre y el sujeto no vuelve a poder avisar nunca — que es peor que el
    ruido, porque es silencio permanente sin síntoma.
    """

    firing: list[Subject] = field(default_factory=list)
    #: Los que han vuelto **pasado el colchón**, no los que sólo tocaron el umbral.
    cleared: list[str] = field(default_factory=list)


# --- Lo que las reglas necesitan mirar --------------------------------------
# Puertos de LECTURA, uno por dominio observado. Alertas no importa inventario, ni caja, ni
# messaging: declara qué necesita ver y la raíz de composición le pasa un adaptador. Así una
# regla nueva no arrastra un módulo entero, y el módulo se prueba con dobles triviales.


@dataclass(frozen=True)
class StockLevel:
    """Cuánto hay de un insumo y a partir de cuánto preocupa."""

    ingredient_id: str
    name: str
    current: float
    minimum: float


@dataclass(frozen=True)
class SessionState:
    """Una sesión de WhatsApp de la sucursal, y si está recibiendo."""

    session_id: str
    label: str
    connected: bool


@dataclass(frozen=True)
class OpenCashSession:
    """Una caja abierta y desde cuándo (hora local del negocio)."""

    session_id: str
    opened_at: datetime


class InventoryReader(Protocol):
    async def low_stock(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[StockLevel]:
        """Insumos en o por debajo de su mínimo. Reutiliza el `min_stock` de inventario."""
        ...

    async def stock_for(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, ingredient_ids: list[str]
    ) -> list[StockLevel]:
        """El nivel de insumos concretos — los que tienen una alerta abierta encima.

        Hace falta porque `low_stock` sólo sabe de los que están mal, y para re-armar hay
        que preguntar por los que ESTABAN mal y ver si ya se recuperaron.
        """
        ...


class SessionReader(Protocol):
    async def sessions(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[SessionState]: ...


class CashReader(Protocol):
    async def open_session(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> OpenCashSession | None: ...


@dataclass
class QuotaLevel:
    """Cuánto del saldo del asistente se lleva gastado en el periodo en curso."""

    used_percent: float
    used_units: int
    quota_units: int
    #: El umbral que el dueño puso al comprar el saldo. Viaja con la medida para que el
    #: evaluador no tenga que preguntarle al asistente por su configuración.
    warning_threshold_percent: int


class AssistantQuotaReader(Protocol):
    async def quota(self, tenant_id: uuid.UUID) -> QuotaLevel | None:
        """`None` si el tenant no tiene el asistente: no hay saldo del que avisar."""
        ...


class AlertRuleEvaluator(Protocol):
    """Una regla: código con parámetros, no una condición de texto libre."""

    rule_key: str

    async def evaluate(
        self,
        rule: AlertRule,
        subject_ref: str | None = None,
        open_refs: list[str] | None = None,
    ) -> Evaluation:
        """Los sujetos que deben disparar y los que se recuperaron.

        `subject_ref` acota la evaluación a uno solo — es el camino del job, que gana
        latencia mirando sólo el insumo que se acaba de mover. `None` evalúa todo, que es lo
        que hace el barrido.

        `open_refs` son los sujetos que YA tienen una alerta abierta. Se pasan porque
        "recuperado" sólo se puede responder sobre ellos: preguntar por el estado de los
        cinco mil insumos del catálogo para descubrir que ninguno tenía alerta sería pagar
        la consulta entera en cada pasada.
        """
        ...


class NotificationChannel(Protocol):
    """Por dónde se avisa. Best-effort SIEMPRE: un canal caído no pierde la alerta.

    La alerta ya está en la base de datos cuando se notifica. Si el canal falla, lo que se
    pierde es el aviso, no el hecho — y el barrido siguiente no lo repite porque la alerta
    sigue abierta. Es una elección: preferimos un aviso perdido a cuarenta repetidos.
    """

    async def notify(self, alert: Alert, subject: Subject, kind: str) -> None: ...


class AlertRepository(Protocol):
    """Persistencia de reglas y alertas."""

    async def list_rules(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[AlertRule]: ...

    async def get_rule(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, rule_key: str
    ) -> AlertRule | None: ...

    async def save_rule(self, rule: AlertRule) -> AlertRule: ...

    async def list_enabled_rules(self) -> list[AlertRule]:
        """Todas las reglas encendidas de todos los tenants y sucursales.

        Sin contexto de tenant: es lo que necesita el barrido, y acotarlo a los "activos
        recientemente" es exactamente cómo se pierde la sucursal que lleva muda dos días.
        """
        ...

    async def claim_fire(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        rule_key: str,
        subject_ref: str,
        subject_label: str | None = None,
    ) -> Alert | None:
        """Crea la alerta si no había una abierta para ese sujeto; `None` si ya la había.

        Quien la crea es quien notifica. Lo decide la constraint de unicidad parcial, no un
        `if`: el job y el barrido pueden mirar el mismo tomate a la vez.
        """
        ...

    async def list_open(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[Alert]: ...

    async def get_open(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, rule_key: str, subject_ref: str
    ) -> Alert | None: ...

    async def get_by_id(
        self, tenant_id: uuid.UUID, alert_id: uuid.UUID
    ) -> Alert | None: ...

    async def acknowledge(
        self, tenant_id: uuid.UUID, alert_id: uuid.UUID, employee_id: uuid.UUID, at: datetime
    ) -> Alert | None:
        """Anota quién la tomó. `None` cuando ya no estaba en `fired` — alguien ganó antes."""
        ...

    async def resolve(
        self, tenant_id: uuid.UUID, alert_id: uuid.UUID, at: datetime
    ) -> Alert | None: ...

    async def list_pending_escalation(self, now: datetime) -> list[tuple[Alert, AlertRule]]:
        """Lo que toca escalar: sin tomar, sin silenciar y con su reloj cumplido.

        Dos relojes: el plazo de la regla para el primer mensaje, y las 4 horas del canal para
        los siguientes. De todos los tenants.
        """
        ...

    async def claim_escalation(
        self, tenant_id: uuid.UUID, alert_id: uuid.UUID, at: datetime, not_since: datetime
    ) -> bool:
        """Reclama el derecho a escalar; `False` si otro llegó antes o aún no toca."""
        ...

    async def list_pending_reminders(self, now: datetime) -> list[tuple[Alert, AlertRule]]:
        """Lo que toca recordar por el panel. Salta las reglas con intervalo `0`."""
        ...

    async def claim_reminder(
        self, tenant_id: uuid.UUID, alert_id: uuid.UUID, at: datetime, not_since: datetime
    ) -> bool:
        """Reclama el derecho a recordar; `False` si otro llegó antes o aún no toca."""
        ...

    async def mute_reminders(
        self, tenant_id: uuid.UUID, alert_id: uuid.UUID, at: datetime
    ) -> Alert | None:
        """La tercera salida: calla los avisos SIN tomarla ni cerrarla. Idempotente."""
        ...

    async def employee_name(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> str | None: ...
