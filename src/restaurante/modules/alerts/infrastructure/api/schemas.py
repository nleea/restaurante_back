"""Esquemas del API de alertas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from restaurante.modules.alerts.domain.entities import (
    DEFAULT_ESCALATION_MINUTES,
    DEFAULT_RECOVERY_BUFFER,
    DEFAULT_REMIND_MINUTES,
    Alert,
    AlertRule,
)


class AlertResponse(BaseModel):
    id: uuid.UUID
    rule_key: str
    subject_ref: str
    #: Cómo se llama, para poder pintarlo. `None` sólo en alertas anteriores a este campo.
    subject_label: str | None
    status: str
    fired_at: datetime | None
    acknowledged_at: datetime | None
    acknowledged_by: uuid.UUID | None
    #: Quién la tiene, ya resuelto: que el segundo en verla no repita el trabajo.
    holder_name: str | None = None
    #: La ÚLTIMA vez que salió por WhatsApp, no "si salió": el escalado se repite cada 4 horas.
    last_escalated_at: datetime | None
    #: Puesta = alguien dijo "ya lo sé, cállate". Sigue abierta y sin dueño: el panel lo pinta
    #: distinto de una tomada, porque silenciar no afirma que nadie se haga cargo.
    reminders_muted_at: datetime | None = None

    @classmethod
    def of(cls, alert: Alert, holder_name: str | None = None) -> AlertResponse:
        return cls(
            id=alert.id or uuid.uuid4(),
            rule_key=alert.rule_key,
            subject_ref=alert.subject_ref,
            subject_label=alert.subject_label,
            status=alert.status,
            fired_at=alert.fired_at,
            acknowledged_at=alert.acknowledged_at,
            acknowledged_by=alert.acknowledged_by,
            holder_name=holder_name,
            last_escalated_at=alert.last_escalated_at,
            reminders_muted_at=alert.reminders_muted_at,
        )


class AlertRuleResponse(BaseModel):
    rule_key: str
    is_enabled: bool
    threshold: float | None
    recovery_buffer: float
    remind_every_minutes: int
    escalation_after_minutes: int
    escalate_to_whatsapp: bool

    @classmethod
    def of(cls, rule: AlertRule) -> AlertRuleResponse:
        return cls(
            rule_key=rule.rule_key,
            is_enabled=rule.is_enabled,
            threshold=rule.threshold,
            recovery_buffer=rule.recovery_buffer,
            remind_every_minutes=rule.remind_every_minutes,
            escalation_after_minutes=rule.escalation_after_minutes,
            escalate_to_whatsapp=rule.escalate_to_whatsapp,
        )


class SaveAlertRuleRequest(BaseModel):
    """La configuración de una regla.

    `recovery_buffer` tiene `gt=0` en el esquema Y una validación en el dominio. No es
    redundancia por descuido: el esquema da un 422 legible al formulario, y el dominio
    impide que cualquier otro camino —una siembra, un script— escriba el cero que convierte
    el módulo en una máquina de repetir.
    """

    is_enabled: bool = False
    threshold: float | None = None
    recovery_buffer: float = Field(default=DEFAULT_RECOVERY_BUFFER, gt=0)
    # `ge=0` y no `ge=1`: aquí el cero SÍ es una elección legítima —"avisa una vez y no
    # insistas"— y es la vía de escape del change. Es lo contrario que el colchón, donde el cero
    # es el bug.
    remind_every_minutes: int = Field(default=DEFAULT_REMIND_MINUTES, ge=0)
    escalation_after_minutes: int = Field(default=DEFAULT_ESCALATION_MINUTES, ge=1)
    escalate_to_whatsapp: bool = False

    def to_rule(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, rule_key: str
    ) -> AlertRule:
        return AlertRule(
            tenant_id=tenant_id,
            branch_id=branch_id,
            rule_key=rule_key,
            is_enabled=self.is_enabled,
            threshold=self.threshold,
            recovery_buffer=self.recovery_buffer,
            remind_every_minutes=self.remind_every_minutes,
            escalation_after_minutes=self.escalation_after_minutes,
            escalate_to_whatsapp=self.escalate_to_whatsapp,
        )


class EscalationReachResponse(BaseModel):
    """A cuánta gente llegaría un escalado ahora mismo, y por qué a los demás no.

    Cuatro números para cuatro causas distintas de "no llegó nada", que desde la pantalla se
    parecen todas entre sí y todas a un fallo.
    """

    has_session: bool
    subscribed: int
    #: De los señalados, cuántos tienen un chat de WhatsApp emparejado.
    with_chat: int
    reachable: int


class EscalationRecipientResponse(BaseModel):
    """Una persona señalada para recibir alertas, y si de verdad se le puede escribir."""

    employee_id: uuid.UUID
    name: str
    #: Tiene un chat de WhatsApp emparejado. Sin él no se le puede escribir, y no se deduce
    #: del teléfono: en modo privacidad WhatsApp nunca nos da el número.
    has_chat: bool
    #: Y ese chat sigue siendo válido para escribir (escribieron ellos primero).
    reachable: bool


class ContactableChatResponse(BaseModel):
    """Un chat al que SE PUEDE escribir: alguien que ya escribió al número del negocio.

    Es la lista de la que se empareja a un empleado. No se pide el teléfono porque puede no
    haberlo: en modo privacidad WhatsApp manda un `@lid`, y eso es todo lo que hay.
    """

    contact_id: uuid.UUID
    #: El nombre que WhatsApp muestra, que es lo único con lo que reconocerlo.
    name: str | None
    #: Número o `@lid`, tal y como se le escribiría.
    address: str


class LinkChatRequest(BaseModel):
    """Con qué chat se corresponde esta persona. `null` la desempareja."""

    contact_id: uuid.UUID | None = None
