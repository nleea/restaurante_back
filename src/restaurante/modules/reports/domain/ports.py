"""Ports for the reports module — read-only aggregation queries."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass
class SessionFacts:
    """The cash-session record the Z report is built around."""

    branch_id: uuid.UUID
    cashier_employee_id: uuid.UUID
    opened_at: datetime
    closed_at: datetime | None
    opening_amount: Decimal
    expected_amount: Decimal | None
    counted_amount: Decimal | None
    difference: Decimal | None


@dataclass
class ChannelAgg:
    channel: str
    amount: Decimal
    tickets: int


@dataclass
class PaymentAgg:
    method: str
    amount: Decimal


@dataclass
class DailyAgg:
    day: str  # yyyy-mm-dd
    amount: Decimal


@dataclass
class TopProductAgg:
    variant_id: uuid.UUID
    units: int
    revenue: Decimal


@dataclass
class RecipeItemRow:
    variant_id: uuid.UUID
    ingredient_id: uuid.UUID
    quantity: Decimal


@dataclass
class SoldItemRow:
    channel: str
    variant_id: uuid.UUID
    units: int


@dataclass
class VariantSalesRow:
    variant_id: uuid.UUID
    units: int
    revenue: Decimal


@dataclass
class MoneyFlowRow:
    """A money movement aggregated by payment method and day."""

    method: str
    day: str  # yyyy-mm-dd
    amount: Decimal


@dataclass
class MovementFlowRow:
    """A cash_movements row aggregated by concept, method and day."""

    concept: str
    method: str
    day: str  # yyyy-mm-dd
    amount: Decimal


class ReportsRepository(Protocol):
    async def get_session_facts(
        self, tenant_id: uuid.UUID, cash_session_id: uuid.UUID
    ) -> SessionFacts | None: ...

    async def order_ids_for_session(
        self, tenant_id: uuid.UUID, cash_session_id: uuid.UUID
    ) -> list[uuid.UUID]: ...

    async def channels_for_orders(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> list[ChannelAgg]: ...

    async def payments_for_session(
        self, tenant_id: uuid.UUID, cash_session_id: uuid.UUID
    ) -> list[PaymentAgg]: ...

    async def discount_total(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> Decimal: ...

    async def returns_total(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> tuple[Decimal, int]: ...

    async def withdrawals_total(
        self, tenant_id: uuid.UUID, cash_session_id: uuid.UUID
    ) -> Decimal: ...

    async def order_close_hours(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> list[int]: ...

    async def top_server(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> uuid.UUID | None: ...

    async def top_product(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> tuple[uuid.UUID, int] | None: ...

    async def employee_name(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> str | None: ...

    async def variant_name(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> str | None: ...

    # --- Revenue engine (period-ranged) ------------------------------------
    async def revenue_channels(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
        cashier_employee_id: uuid.UUID | None = None,
    ) -> list[ChannelAgg]: ...

    async def revenue_payments(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[PaymentAgg]: ...

    async def revenue_discounts_returns(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> tuple[Decimal, Decimal, int]: ...

    async def daily_income(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[DailyAgg]: ...

    async def daily_expenses(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[DailyAgg]: ...

    async def top_products(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
        limit: int,
    ) -> list[TopProductAgg]: ...

    # --- Product costing (COGS) --------------------------------------------
    async def ingredient_avg_costs(
        self, tenant_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, Decimal]]: ...

    async def all_recipe_items(
        self, tenant_id: uuid.UUID
    ) -> list[RecipeItemRow]: ...

    async def sold_items_by_channel(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[SoldItemRow]: ...

    # --- Profitability (P&L, margins) --------------------------------------
    async def expenses_total(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> Decimal: ...

    async def labor_expenses_total(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> Decimal | None: ...

    async def variant_sales(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[VariantSalesRow]: ...

    # --- Cash flow (money-in / money-out) ----------------------------------
    async def cf_sales(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[MoneyFlowRow]: ...

    async def cf_supplier_payments(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[MoneyFlowRow]: ...

    async def cf_expenses(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[tuple[str, Decimal]]: ...

    async def cf_movements(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
        direction: str,
    ) -> list[MovementFlowRow]: ...
