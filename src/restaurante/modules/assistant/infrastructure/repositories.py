"""Persistencia del asistente. Lecturas baratas, escrituras que sólo añaden.

`units_used` es la consulta del camino caliente: se ejecuta ANTES de cada llamada al modelo,
así que va contra el índice `(tenant_id, occurred_at)` y suma en la base en vez de traerse el
periodo entero para contarlo en Python.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.assistant.domain.entities import (
    AssistantConversationState,
    AssistantEntitlement,
    ConversationTurn,
    UsageEntry,
)
from restaurante.modules.assistant.infrastructure.models import (
    AssistantConversationStateModel,
    AssistantEntitlementModel,
    AssistantUsageLedgerModel,
)


def _as_utc(value: datetime) -> datetime:
    """SQLite devuelve los instantes sin zona; Postgres con ella."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class SqlAlchemyAssistantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Derecho ------------------------------------------------------------
    async def get_entitlement(
        self, tenant_id: uuid.UUID
    ) -> AssistantEntitlement | None:
        row = (
            await self._session.execute(
                select(AssistantEntitlementModel).where(
                    AssistantEntitlementModel.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return AssistantEntitlement(
            tenant_id=row.tenant_id,
            plan=row.plan,
            is_enabled=row.is_enabled,
            monthly_quota_units=row.monthly_quota_units,
            period_anchor=_as_utc(row.period_anchor) if row.period_anchor else None,
            warning_threshold_percent=row.warning_threshold_percent,
            fallback_message=row.fallback_message,
            id=row.id,
        )

    async def save_entitlement(
        self, entitlement: AssistantEntitlement
    ) -> AssistantEntitlement:
        row = (
            await self._session.execute(
                select(AssistantEntitlementModel).where(
                    AssistantEntitlementModel.tenant_id == entitlement.tenant_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = AssistantEntitlementModel(tenant_id=entitlement.tenant_id)
            self._session.add(row)
        row.plan = entitlement.plan
        row.is_enabled = entitlement.is_enabled
        row.monthly_quota_units = entitlement.monthly_quota_units
        # El ancla se fija la primera vez y no se mueve: cambiarla al guardar reiniciaría el
        # periodo —y con él el consumo— cada vez que alguien toca la pantalla.
        row.period_anchor = row.period_anchor or entitlement.period_anchor or datetime.now(UTC)
        row.warning_threshold_percent = entitlement.warning_threshold_percent
        row.fallback_message = entitlement.fallback_message
        await self._session.commit()
        await self._session.refresh(row)
        stored = await self.get_entitlement(entitlement.tenant_id)
        assert stored is not None  # noqa: S101 - se acaba de escribir
        return stored

    # --- Libro mayor --------------------------------------------------------
    async def record_usage(self, entry: UsageEntry) -> UsageEntry:
        row = AssistantUsageLedgerModel(
            tenant_id=entry.tenant_id,
            occurred_at=entry.occurred_at,
            caller_kind=entry.caller_kind,
            conversation_ref=entry.conversation_ref,
            provider=entry.provider,
            model=entry.model,
            tokens_in=entry.tokens_in,
            tokens_out=entry.tokens_out,
            provider_cost=entry.provider_cost,
            billed_units=entry.billed_units,
        )
        self._session.add(row)
        await self._session.commit()
        entry.id = row.id
        return entry

    async def units_used(
        self, tenant_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> int:
        total = (
            await self._session.execute(
                select(func.coalesce(func.sum(AssistantUsageLedgerModel.billed_units), 0))
                .where(AssistantUsageLedgerModel.tenant_id == tenant_id)
                .where(AssistantUsageLedgerModel.occurred_at >= period_start)
                .where(AssistantUsageLedgerModel.occurred_at < period_end)
            )
        ).scalar_one()
        return int(total or 0)

    async def usage_cost(
        self, tenant_id: uuid.UUID, period_start: datetime, period_end: datetime
    ) -> Decimal:
        total = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(AssistantUsageLedgerModel.provider_cost), 0)
                )
                .where(AssistantUsageLedgerModel.tenant_id == tenant_id)
                .where(AssistantUsageLedgerModel.occurred_at >= period_start)
                .where(AssistantUsageLedgerModel.occurred_at < period_end)
            )
        ).scalar_one()
        return Decimal(str(total or 0))

    async def recent_usage(
        self, tenant_id: uuid.UUID, limit: int = 20
    ) -> list[UsageEntry]:
        rows = (
            await self._session.execute(
                select(AssistantUsageLedgerModel)
                .where(AssistantUsageLedgerModel.tenant_id == tenant_id)
                .order_by(AssistantUsageLedgerModel.occurred_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            UsageEntry(
                tenant_id=row.tenant_id,
                occurred_at=_as_utc(row.occurred_at),
                caller_kind=row.caller_kind,
                provider=row.provider,
                model=row.model,
                tokens_in=row.tokens_in,
                tokens_out=row.tokens_out,
                provider_cost=Decimal(str(row.provider_cost)),
                billed_units=row.billed_units,
                conversation_ref=row.conversation_ref,
                id=row.id,
            )
            for row in rows
        ]

    # --- Estado de conversación ---------------------------------------------
    async def get_state(
        self, tenant_id: uuid.UUID, conversation_ref: str
    ) -> AssistantConversationState | None:
        row = (
            await self._session.execute(
                select(AssistantConversationStateModel)
                .where(AssistantConversationStateModel.tenant_id == tenant_id)
                .where(
                    AssistantConversationStateModel.conversation_ref == conversation_ref
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return AssistantConversationState(
            tenant_id=row.tenant_id,
            conversation_ref=row.conversation_ref,
            caller_kind=row.caller_kind,
            turns=[_turn(item) for item in row.turns],
            branch_id=row.branch_id,
            last_turn_at=_as_utc(row.last_turn_at) if row.last_turn_at else None,
            id=row.id,
        )

    async def save_state(
        self, state: AssistantConversationState
    ) -> AssistantConversationState:
        row = (
            await self._session.execute(
                select(AssistantConversationStateModel)
                .where(AssistantConversationStateModel.tenant_id == state.tenant_id)
                .where(
                    AssistantConversationStateModel.conversation_ref
                    == state.conversation_ref
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = AssistantConversationStateModel(
                tenant_id=state.tenant_id,
                conversation_ref=state.conversation_ref,
            )
            self._session.add(row)
        row.caller_kind = state.caller_kind
        row.branch_id = state.branch_id
        row.turns = [{"role": t.role, "text": t.text} for t in state.turns]
        row.last_turn_at = state.last_turn_at or datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(row)
        state.id = row.id
        return state


def _turn(item: dict[str, Any]) -> ConversationTurn:
    return ConversationTurn(role=str(item.get("role", "")), text=str(item.get("text", "")))
