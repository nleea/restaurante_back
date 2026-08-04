"""Esquemas del API del asistente."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from restaurante.modules.assistant.application.use_cases.metering import (
    AssistantAnswer,
    UsageStatus,
)
from restaurante.modules.assistant.domain.entities import (
    DEFAULT_WARNING_THRESHOLD_PERCENT,
    AssistantEntitlement,
)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    branch_id: uuid.UUID


class AskResponse(BaseModel):
    """La respuesta y lo que costó.

    El coste viaja de vuelta porque quien pregunta desde el panel suele ser quien paga: ver
    el gasto en el momento es lo que evita descubrirlo en la factura.
    """

    text: str
    model: str
    tokens_in: int
    tokens_out: int
    billed_units: int

    @classmethod
    def of(cls, answer: AssistantAnswer) -> AskResponse:
        return cls(
            text=answer.text,
            model=answer.model,
            tokens_in=answer.tokens_in,
            tokens_out=answer.tokens_out,
            billed_units=answer.billed_units,
        )


class UsageResponse(BaseModel):
    entitled: bool
    is_enabled: bool
    plan: str
    quota_units: int
    used_units: int
    remaining_units: int
    used_percent: float
    exhausted: bool
    warning_threshold_percent: int
    period_start: datetime | None
    period_end: datetime | None
    provider_cost: Decimal

    @classmethod
    def of(cls, status: UsageStatus) -> UsageResponse:
        return cls(
            entitled=status.entitled,
            is_enabled=status.is_enabled,
            plan=status.plan,
            quota_units=status.quota_units,
            used_units=status.used_units,
            remaining_units=status.remaining_units,
            used_percent=status.used_percent,
            exhausted=status.exhausted,
            warning_threshold_percent=status.warning_threshold_percent,
            period_start=status.period_start,
            period_end=status.period_end,
            provider_cost=status.provider_cost,
        )


class UsageEntryResponse(BaseModel):
    occurred_at: datetime
    caller_kind: str
    model: str
    tokens_in: int
    tokens_out: int
    billed_units: int
    provider_cost: Decimal


class SaveEntitlementRequest(BaseModel):
    plan: str = Field(min_length=1, max_length=40)
    is_enabled: bool = False
    monthly_quota_units: int = Field(ge=0)
    warning_threshold_percent: int = Field(
        default=DEFAULT_WARNING_THRESHOLD_PERCENT, ge=1, le=99
    )
    fallback_message: str = Field(default="", max_length=1000)

    def to_entity(self, tenant_id: uuid.UUID) -> AssistantEntitlement:
        return AssistantEntitlement(
            tenant_id=tenant_id,
            plan=self.plan,
            is_enabled=self.is_enabled,
            monthly_quota_units=self.monthly_quota_units,
            warning_threshold_percent=self.warning_threshold_percent,
            fallback_message=self.fallback_message,
        )


class PlanResponse(BaseModel):
    """Lo que la pantalla necesita para explicar un plan. Sin precios de proveedor.

    Lo que nos cuesta a nosotros no es asunto del tenant: enseñárselo sería enseñarle el
    margen.
    """

    name: str
    max_input_tokens: int
    max_output_tokens: int
