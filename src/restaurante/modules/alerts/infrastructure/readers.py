"""Adaptadores de lectura: lo que las reglas miran en otros módulos.

Sólo `SELECT`. Alertas no escribe en inventario, ni en caja, ni en messaging — observa. Que
sean lecturas directas sobre los modelos y no los repositorios ajenos es deliberado: un
repositorio trae su propio ciclo de vida y sus escrituras, y aquí sólo hacen falta tres
consultas. La abstracción que importa ya está en el puerto.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.alerts.domain.ports import (
    OpenCashSession,
    QuotaLevel,
    SessionState,
    StockLevel,
)
from restaurante.modules.assistant.domain.entities import period_bounds
from restaurante.modules.assistant.infrastructure.models import (
    AssistantEntitlementModel,
    AssistantUsageLedgerModel,
)
from restaurante.modules.cash.infrastructure.models import CashSessionModel
from restaurante.modules.inventory.infrastructure.models import InventoryStockModel
from restaurante.modules.messaging.infrastructure.models import WhatsAppSessionModel
from restaurante.modules.recipes.infrastructure.models import IngredientModel


class SqlAlchemyInventoryReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def low_stock(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[StockLevel]:
        # El mismo predicado que `InventoryRepository.list_low_stock`, con el nombre del
        # insumo unido: la alerta tiene que poder decir "Tomate", no un uuid.
        stmt = (
            select(
                InventoryStockModel.ingredient_id,
                IngredientModel.name,
                InventoryStockModel.current_quantity,
                InventoryStockModel.min_stock,
            )
            .select_from(InventoryStockModel)
            .join(
                IngredientModel,
                IngredientModel.id == InventoryStockModel.ingredient_id,
            )
            .where(
                InventoryStockModel.tenant_id == tenant_id,
                InventoryStockModel.branch_id == branch_id,
                InventoryStockModel.current_quantity <= InventoryStockModel.min_stock,
            )
            .order_by(IngredientModel.name)
        )
        return [_level(row) for row in (await self._session.execute(stmt)).all()]

    async def stock_for(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, ingredient_ids: list[str]
    ) -> list[StockLevel]:
        ids = [uuid.UUID(value) for value in ingredient_ids if _is_uuid(value)]
        if not ids:
            return []
        stmt = (
            select(
                InventoryStockModel.ingredient_id,
                IngredientModel.name,
                InventoryStockModel.current_quantity,
                InventoryStockModel.min_stock,
            )
            .select_from(InventoryStockModel)
            .join(
                IngredientModel,
                IngredientModel.id == InventoryStockModel.ingredient_id,
            )
            .where(
                InventoryStockModel.tenant_id == tenant_id,
                InventoryStockModel.branch_id == branch_id,
                InventoryStockModel.ingredient_id.in_(ids),
            )
        )
        return [_level(row) for row in (await self._session.execute(stmt)).all()]


class SqlAlchemySessionReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def sessions(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[SessionState]:
        stmt = select(WhatsAppSessionModel).where(
            WhatsAppSessionModel.tenant_id == tenant_id,
            WhatsAppSessionModel.branch_id == branch_id,
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            SessionState(
                session_id=str(row.id),
                label=row.phone_number or row.provider_instance_ref,
                # `banned` y `disconnected` son ambos "no recibe". La diferencia importa para
                # arreglarlo, no para saber que la sucursal está muda.
                connected=row.status == "connected",
            )
            for row in rows
        ]


class SqlAlchemyCashReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def open_session(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> OpenCashSession | None:
        stmt = (
            select(CashSessionModel)
            .where(
                CashSessionModel.tenant_id == tenant_id,
                CashSessionModel.branch_id == branch_id,
                CashSessionModel.status == "open",
            )
            .order_by(CashSessionModel.opened_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return OpenCashSession(session_id=str(row.id), opened_at=row.opened_at)


def _level(row: Row[tuple[uuid.UUID, str, Decimal, Decimal]]) -> StockLevel:
    """Las cantidades salen como `Decimal` y se guardan como `float`.

    Aquí es correcto: el colchón y el mínimo se comparan, no se suman a un total de dinero.
    Lo que NO puede pasar es que un `Decimal` de inventario acabe en un precio, y no lo hace.
    """
    ingredient_id, name, current, minimum = row.tuple()
    return StockLevel(
        ingredient_id=str(ingredient_id),
        name=name,
        current=float(current or 0),
        minimum=float(minimum or 0),
    )


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


class SqlAlchemyAssistantQuotaReader:
    """Cuánto saldo del asistente lleva gastado el tenant en el periodo en curso.

    Misma postura que los otros lectores: `SELECT` directo sobre los modelos del módulo
    observado, sin pasar por su repositorio. Aquí además importa por qué: el barrido corre
    sin contexto de tenant y necesita medir a todos, mientras que el caso de uso del
    asistente mide al de la petición en curso.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def quota(self, tenant_id: uuid.UUID) -> QuotaLevel | None:
        row = (
            await self._session.execute(
                select(AssistantEntitlementModel).where(
                    AssistantEntitlementModel.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        if row is None or not row.is_enabled or row.monthly_quota_units <= 0:
            # Sin derecho, apagado o sin unidades: no hay saldo del que avisar. Devolver 100%
            # aquí haría que encender la regla avisara de todos los tenants que no compraron.
            return None

        anchor = row.period_anchor or datetime.now(UTC)
        start, end = period_bounds(_as_utc(anchor), datetime.now(UTC))
        used = int(
            (
                await self._session.execute(
                    select(
                        func.coalesce(
                            func.sum(AssistantUsageLedgerModel.billed_units), 0
                        )
                    )
                    .where(AssistantUsageLedgerModel.tenant_id == tenant_id)
                    .where(AssistantUsageLedgerModel.occurred_at >= start)
                    .where(AssistantUsageLedgerModel.occurred_at < end)
                )
            ).scalar_one()
            or 0
        )
        return QuotaLevel(
            used_percent=round(used * 100 / row.monthly_quota_units, 2),
            used_units=used,
            quota_units=row.monthly_quota_units,
            warning_threshold_percent=row.warning_threshold_percent,
        )


def _as_utc(value: datetime) -> datetime:
    """SQLite devuelve los instantes sin zona; Postgres con ella."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)
