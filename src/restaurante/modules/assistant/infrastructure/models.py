"""Modelos ORM del asistente: derecho, libro mayor y estado de conversación.

Las tres son de TENANT, no de sucursal: el asistente se compra por negocio, y una cuota por
sede convertiría "se me acabó" en cuatro preguntas distintas. La sucursal sí viaja en el
estado de la conversación, porque "¿cuánto vendimos ayer?" no significa lo mismo en dos
sedes.

`assistant_usage_ledger` es de sólo-añadir. No hay `updated_at` a propósito: una fila que se
puede editar no es un libro mayor, es un contador con historia decorativa, y la pregunta que
justifica todo esto —"¿por qué me cobraste esto?"— deja de tener respuesta.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.modules.assistant.domain.entities import (
    DEFAULT_PLAN,
    DEFAULT_WARNING_THRESHOLD_PERCENT,
)
from restaurante.shared.database import Base, TenantScopedMixin, TimestampMixin


class AssistantEntitlementModel(Base, TenantScopedMixin, TimestampMixin):
    """Lo que un tenant compró. Una fila por tenant, o ninguna.

    Ninguna fila = ningún derecho, que es el estado de TODOS al instalar este cambio: sin
    ella no se llama al modelo ni una vez, y el sistema se comporta exactamente como antes.
    """

    __tablename__ = "assistant_entitlements"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_assistant_entitlements_tenant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    plan: Mapped[str] = mapped_column(String(40), nullable=False, default=DEFAULT_PLAN)
    # Apagado aunque exista la fila: vender unidades y encender el asistente son dos
    # decisiones, y confundirlas hace que comprar saldo lo encienda sin que nadie lo pida.
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    monthly_quota_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    period_anchor: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    warning_threshold_percent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_WARNING_THRESHOLD_PERCENT
    )
    fallback_message: Mapped[str] = mapped_column(Text, nullable=False, default="")


class AssistantUsageLedgerModel(Base, TenantScopedMixin):
    """Una fila por llamada al modelo. Sólo se añade.

    El índice `(tenant_id, occurred_at)` no es higiene: el saldo es una PROYECCIÓN sobre esta
    tabla y se consulta ANTES de cada llamada, así que es lo único que separa "el guardián del
    dinero" de "la parte más lenta de contestar un mensaje".
    """

    __tablename__ = "assistant_usage_ledger"
    __table_args__ = (
        Index("ix_assistant_ledger_tenant_period", "tenant_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    caller_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # Texto libre y no una FK: apunta tanto a una conversación de WhatsApp como al chat de
    # administración de un empleado, y una FK sólo podría apuntar a una de las dos.
    conversation_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Lo que nos costó a NOSOTROS. Seis decimales porque una llamada barata cuesta millonésimas
    # de dólar y redondear a céntimos aquí es contar cero un millón de veces.
    provider_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False, default=Decimal("0")
    )
    # Lo que se le facturó al tenant, en unidades de su cuota. La otra capa.
    billed_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AssistantConversationStateModel(Base, TenantScopedMixin, TimestampMixin):
    """El hilo como lo ve el asistente, separado del hilo humano de WhatsApp.

    `conversation_ref` lleva su origen dentro (`whatsapp:<uuid>`, `admin:<uuid>`) para que las
    dos vías compartan tabla sin dos columnas nulas excluyentes.
    """

    __tablename__ = "assistant_conversation_state"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "conversation_ref", name="uq_assistant_state_conversation"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    caller_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # La sucursal en la que se pregunta. Nula para un cliente que aún no eligió sede.
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Los turnos YA recortados a la ventana. Guardar más sería pagar por guardar lo que nunca
    # se envía: la historia es el principal motor del coste de entrada.
    turns: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    last_turn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
