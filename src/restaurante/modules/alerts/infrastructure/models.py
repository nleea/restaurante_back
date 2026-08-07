"""Modelos ORM del módulo de alertas: `alert_rules` y `alerts`.

Dos tablas, y la forma de sus constraints ES el diseño:

- `alert_rules` lleva un `UNIQUE(tenant, branch, rule_key)`: una regla se configura por
  sucursal, y encenderla en una no la enciende en las demás.
- `alerts` lleva un índice único PARCIAL sobre `(tenant, branch, rule_key, subject_ref)`
  limitado a las alertas abiertas. Es lo que garantiza "avisar una vez": mientras el tomate
  siga bajo y su alerta siga abierta, ninguna evaluación —ni el job ni el barrido— puede
  crear una segunda. Lo impide la base de datos, no un `if ya_avisamos`, que es la misma
  forma que ya usan las emisiones del autoreply y la toma de una conversación del inbox.

El estado `armed` no tiene fila. Una alerta armada es la AUSENCIA de una abierta para ese
sujeto; guardarla obligaría a crear una fila por cada ingrediente de cada sucursal antes de
que pasara nada.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.modules.alerts.domain.entities import (
    ALERT_FIRED,
    DEFAULT_ESCALATION_MINUTES,
    DEFAULT_RECOVERY_BUFFER,
    DEFAULT_REMIND_MINUTES,
    OPEN_ALERT_STATUSES,
)
from restaurante.shared.database import Base, BranchScopedMixin, TimestampMixin

# El `WHERE` del índice parcial. Se escribe con `text()` y no con la columna porque el índice
# se declara antes de que la clase exista; el predicado es idéntico en Postgres y en SQLite,
# así que el test que corre en SQLite prueba la MISMA garantía que producción.
_OPEN_STATUSES_LITERAL = ", ".join(f"'{status}'" for status in OPEN_ALERT_STATUSES)
OPEN_ALERT_PREDICATE = text(f"status IN ({_OPEN_STATUSES_LITERAL})")


class AlertRuleModel(Base, BranchScopedMixin, TimestampMixin):
    """Una condición configurada para una sucursal."""

    __tablename__ = "alert_rules"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "branch_id", "rule_key", name="uq_alert_rules_branch_key"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rule_key: Mapped[str] = mapped_column(String(60), nullable=False)
    # Se siembra apagada. Instalar el change no puede cambiarle el comportamiento a nadie.
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Opcional y con significado por regla; ver `AlertRule`.
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    recovery_buffer: Mapped[float] = mapped_column(
        Float, nullable=False, default=DEFAULT_RECOVERY_BUFFER
    )
    # Cada cuánto insiste el PANEL mientras nadie la toque. `0` = avisa una vez y calla, que es
    # como se comportaba el módulo antes de que esto existiera y sigue siendo la vía de escape.
    remind_every_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_REMIND_MINUTES, server_default=text("5")
    )
    escalation_after_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_ESCALATION_MINUTES
    )
    escalate_to_whatsapp: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


class AlertModel(Base, BranchScopedMixin, TimestampMixin):
    """Una instancia de una regla disparada sobre un sujeto."""

    __tablename__ = "alerts"
    __table_args__ = (
        # El corazón del módulo: como mucho UNA alerta abierta por sujeto. Parcial, porque
        # las resueltas se conservan —"cuántas veces nos quedamos sin tomate" es el informe
        # que alguien va a pedir— y dos episodios distintos del mismo tomate son dos filas.
        Index(
            "uq_alerts_open_subject",
            "tenant_id",
            "branch_id",
            "rule_key",
            "subject_ref",
            unique=True,
            postgresql_where=OPEN_ALERT_PREDICATE,
            sqlite_where=OPEN_ALERT_PREDICATE,
        ),
        Index("ix_alerts_branch_status", "branch_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rule_key: Mapped[str] = mapped_column(String(60), nullable=False)
    # De quién habla: el ingrediente, la sesión de WhatsApp o la de caja. Texto y no FK a
    # propósito: apunta a tablas de tres módulos, y una FK por regla convertiría añadir una
    # regla en una migración.
    subject_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    # Cómo se llama eso, guardado al disparar. Volver a deducirlo falla justo en el hueco de
    # la histéresis, y entonces el aviso sale con un uuid. Ver la migración 0027.
    subject_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ALERT_FIRED)
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # La ÚLTIMA vez que se gastó un mensaje de WhatsApp en ella — no "si se gastó". Se anota
    # aunque el envío falle: es lo que marca el ritmo de 4 horas en vez de reintentar en cada
    # barrido. El nombre cambió con el escalado repetido; la columna es la misma.
    last_escalated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # La última vez que el panel avisó de ella. **El disparo cuenta como aviso**: si no, el
    # primer recordatorio saldría en el barrido siguiente en vez de un intervalo después.
    last_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # "Ya lo sé, cállate". La tercera salida: deja de recordar sin que nadie se haga cargo y sin
    # tocar `status`, así que la alerta sigue abierta, sin dueño y visible en el panel.
    reminders_muted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
