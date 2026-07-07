"""Read-only aggregation adapter for finance reporting.

This module reads OTHER modules' tables directly (orders, cash) — a deliberate
cross-cutting read layer. It never writes and never imports their write
use-cases; only their ORM models, to aggregate.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.cash.infrastructure.models import (
    CashMovementModel,
    CashSessionModel,
)
from restaurante.modules.finance.infrastructure.models import (
    ExpenseCategoryModel,
    ExpenseModel,
)
from restaurante.modules.identity.infrastructure.models import PersonModel
from restaurante.modules.menu.infrastructure.models import (
    ProductModel,
    ProductVariantModel,
)
from restaurante.modules.orders.infrastructure.models import (
    OrderItemModel,
    OrderModel,
    OrderPaymentModel,
)
from restaurante.modules.purchasing.infrastructure.models import (
    PurchaseOrderItemModel,
    PurchaseOrderModel,
    PurchasePaymentModel,
)
from restaurante.modules.recipes.infrastructure.models import RecipeItemModel
from restaurante.modules.reports.domain.ports import (
    ChannelAgg,
    DailyAgg,
    MoneyFlowRow,
    MovementFlowRow,
    PaymentAgg,
    RecipeItemRow,
    SessionFacts,
    SoldItemRow,
    TopProductAgg,
    VariantSalesRow,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel

_ORDER_CLOSED = "closed"
_ITEM_CANCELLED = "cancelled"
_MOVEMENT_IN = "in"
_MOVEMENT_OUT = "out"
# cash_movements concepts that mirror a source table and must NOT be re-summed
# from the movement ledger (they are read from their own tables instead).
_CONCEPT_SALE = "sale"
_CONCEPT_PURCHASE_PAYMENT = "purchase_payment"
# Expense categories whose name marks them as labor cost (case-insensitive
# substring match). Used for the labor-cost / prime-cost manager KPIs.
_LABOR_KEYWORDS = ("nómina", "nomina", "salario", "sueldo", "personal", "labor")


def _dec(value: Decimal | None) -> Decimal:
    return value if value is not None else Decimal(0)


class SqlAlchemyReportsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_session_facts(
        self, tenant_id: uuid.UUID, cash_session_id: uuid.UUID
    ) -> SessionFacts | None:
        stmt = select(CashSessionModel).where(
            CashSessionModel.id == cash_session_id,
            CashSessionModel.tenant_id == tenant_id,
        )
        m = (await self._session.execute(stmt)).scalar_one_or_none()
        if m is None:
            return None
        return SessionFacts(
            branch_id=m.branch_id,
            cashier_employee_id=m.opened_by_employee_id,
            opened_at=m.opened_at,
            closed_at=m.closed_at,
            opening_amount=m.opening_amount,
            expected_amount=m.expected_amount,
            counted_amount=m.counted_amount,
            difference=m.difference,
        )

    async def order_ids_for_session(
        self, tenant_id: uuid.UUID, cash_session_id: uuid.UUID
    ) -> list[uuid.UUID]:
        stmt = (
            select(OrderPaymentModel.order_id)
            .where(
                OrderPaymentModel.tenant_id == tenant_id,
                OrderPaymentModel.cash_session_id == cash_session_id,
            )
            .distinct()
        )
        return list((await self._session.execute(stmt)).scalars())

    async def channels_for_orders(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> list[ChannelAgg]:
        if not order_ids:
            return []
        stmt = (
            select(
                OrderModel.channel,
                func.sum(OrderModel.total),
                func.count(OrderModel.id),
            )
            .where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.id.in_(order_ids),
                OrderModel.status == _ORDER_CLOSED,
            )
            .group_by(OrderModel.channel)
        )
        rows = (await self._session.execute(stmt)).all()
        return [ChannelAgg(channel=r[0], amount=_dec(r[1]), tickets=r[2]) for r in rows]

    async def payments_for_session(
        self, tenant_id: uuid.UUID, cash_session_id: uuid.UUID
    ) -> list[PaymentAgg]:
        stmt = (
            select(OrderPaymentModel.method, func.sum(OrderPaymentModel.amount))
            .where(
                OrderPaymentModel.tenant_id == tenant_id,
                OrderPaymentModel.cash_session_id == cash_session_id,
            )
            .group_by(OrderPaymentModel.method)
        )
        rows = (await self._session.execute(stmt)).all()
        return [PaymentAgg(method=r[0], amount=_dec(r[1])) for r in rows]

    async def discount_total(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> Decimal:
        if not order_ids:
            return Decimal(0)
        stmt = select(func.sum(OrderModel.discount)).where(
            OrderModel.tenant_id == tenant_id,
            OrderModel.id.in_(order_ids),
            OrderModel.status == _ORDER_CLOSED,
        )
        return _dec((await self._session.execute(stmt)).scalar_one_or_none())

    async def returns_total(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> tuple[Decimal, int]:
        if not order_ids:
            return Decimal(0), 0
        stmt = select(
            func.sum(OrderItemModel.line_subtotal), func.count(OrderItemModel.id)
        ).where(
            OrderItemModel.tenant_id == tenant_id,
            OrderItemModel.order_id.in_(order_ids),
            OrderItemModel.status == _ITEM_CANCELLED,
        )
        row = (await self._session.execute(stmt)).one()
        return _dec(row[0]), row[1] or 0

    async def withdrawals_total(
        self, tenant_id: uuid.UUID, cash_session_id: uuid.UUID
    ) -> Decimal:
        stmt = select(func.sum(CashMovementModel.amount)).where(
            CashMovementModel.tenant_id == tenant_id,
            CashMovementModel.cash_session_id == cash_session_id,
            CashMovementModel.type == _MOVEMENT_OUT,
        )
        return _dec((await self._session.execute(stmt)).scalar_one_or_none())

    async def order_close_hours(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> list[int]:
        if not order_ids:
            return []
        stmt = select(OrderModel.closed_at).where(
            OrderModel.tenant_id == tenant_id,
            OrderModel.id.in_(order_ids),
            OrderModel.closed_at.is_not(None),
        )
        return [d.hour for d in (await self._session.execute(stmt)).scalars() if d]

    async def top_server(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> uuid.UUID | None:
        if not order_ids:
            return None
        stmt = (
            select(OrderModel.employee_id, func.sum(OrderModel.total).label("t"))
            .where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.id.in_(order_ids),
                OrderModel.status == _ORDER_CLOSED,
            )
            .group_by(OrderModel.employee_id)
            .order_by(func.sum(OrderModel.total).desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def top_product(
        self, tenant_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> tuple[uuid.UUID, int] | None:
        if not order_ids:
            return None
        stmt = (
            select(
                OrderItemModel.product_variant_id,
                func.sum(OrderItemModel.quantity).label("q"),
            )
            .where(
                OrderItemModel.tenant_id == tenant_id,
                OrderItemModel.order_id.in_(order_ids),
                OrderItemModel.status != _ITEM_CANCELLED,
            )
            .group_by(OrderItemModel.product_variant_id)
            .order_by(func.sum(OrderItemModel.quantity).desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).first()
        return (row[0], int(row[1])) if row else None

    async def employee_name(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> str | None:
        stmt = (
            select(PersonModel.first_name, PersonModel.last_name)
            .join(EmployeeModel, EmployeeModel.person_id == PersonModel.id)
            .where(
                EmployeeModel.id == employee_id,
                EmployeeModel.tenant_id == tenant_id,
            )
        )
        row = (await self._session.execute(stmt)).first()
        return f"{row[0]} {row[1]}".strip() if row else None

    async def variant_name(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> str | None:
        stmt = (
            select(ProductVariantModel.name, ProductModel.name)
            .join(ProductModel, ProductModel.id == ProductVariantModel.product_id)
            .where(
                ProductVariantModel.id == variant_id,
                ProductVariantModel.tenant_id == tenant_id,
            )
        )
        row = (await self._session.execute(stmt)).first()
        if not row:
            return None
        value = row[0] or row[1]
        return str(value) if value is not None else None

    # --- Revenue engine (period-ranged) ------------------------------------
    async def revenue_channels(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
        cashier_employee_id: uuid.UUID | None = None,
    ) -> list[ChannelAgg]:
        stmt = (
            select(
                OrderModel.channel,
                func.sum(OrderModel.total),
                func.count(OrderModel.id),
            )
            .where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.branch_id == branch_id,
                OrderModel.status == _ORDER_CLOSED,
                func.date(OrderModel.closed_at).between(date_from, date_to),
            )
            .group_by(OrderModel.channel)
        )
        if cashier_employee_id is not None:
            stmt = stmt.where(OrderModel.employee_id == cashier_employee_id)
        rows = (await self._session.execute(stmt)).all()
        return [ChannelAgg(channel=r[0], amount=_dec(r[1]), tickets=r[2]) for r in rows]

    async def revenue_payments(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[PaymentAgg]:
        stmt = (
            select(OrderPaymentModel.method, func.sum(OrderPaymentModel.amount))
            .join(OrderModel, OrderModel.id == OrderPaymentModel.order_id)
            .where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.branch_id == branch_id,
                OrderModel.status == _ORDER_CLOSED,
                func.date(OrderModel.closed_at).between(date_from, date_to),
            )
            .group_by(OrderPaymentModel.method)
        )
        rows = (await self._session.execute(stmt)).all()
        return [PaymentAgg(method=r[0], amount=_dec(r[1])) for r in rows]

    async def revenue_discounts_returns(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> tuple[Decimal, Decimal, int]:
        disc_stmt = select(func.sum(OrderModel.discount)).where(
            OrderModel.tenant_id == tenant_id,
            OrderModel.branch_id == branch_id,
            OrderModel.status == _ORDER_CLOSED,
            func.date(OrderModel.closed_at).between(date_from, date_to),
        )
        discounts = _dec((await self._session.execute(disc_stmt)).scalar_one_or_none())
        ret_stmt = (
            select(
                func.sum(OrderItemModel.line_subtotal),
                func.count(OrderItemModel.id),
            )
            .join(OrderModel, OrderModel.id == OrderItemModel.order_id)
            .where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.branch_id == branch_id,
                func.date(OrderModel.closed_at).between(date_from, date_to),
                OrderItemModel.status == _ITEM_CANCELLED,
            )
        )
        ret_row = (await self._session.execute(ret_stmt)).one()
        return discounts, _dec(ret_row[0]), ret_row[1] or 0

    async def daily_income(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[DailyAgg]:
        day = func.date(OrderModel.closed_at)
        stmt = (
            select(day, func.sum(OrderModel.total))
            .where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.branch_id == branch_id,
                OrderModel.status == _ORDER_CLOSED,
                day.between(date_from, date_to),
            )
            .group_by(day)
        )
        rows = (await self._session.execute(stmt)).all()
        return [DailyAgg(day=str(r[0])[:10], amount=_dec(r[1])) for r in rows]

    async def daily_expenses(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[DailyAgg]:
        day = func.date(ExpenseModel.incurred_at)
        stmt = (
            select(day, func.sum(ExpenseModel.amount))
            .where(
                ExpenseModel.tenant_id == tenant_id,
                ExpenseModel.branch_id == branch_id,
                day.between(date_from, date_to),
            )
            .group_by(day)
        )
        rows = (await self._session.execute(stmt)).all()
        return [DailyAgg(day=str(r[0])[:10], amount=_dec(r[1])) for r in rows]

    async def top_products(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
        limit: int,
    ) -> list[TopProductAgg]:
        stmt = (
            select(
                OrderItemModel.product_variant_id,
                func.sum(OrderItemModel.quantity),
                func.sum(OrderItemModel.line_subtotal),
            )
            .join(OrderModel, OrderModel.id == OrderItemModel.order_id)
            .where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.branch_id == branch_id,
                OrderModel.status == _ORDER_CLOSED,
                func.date(OrderModel.closed_at).between(date_from, date_to),
                OrderItemModel.status != _ITEM_CANCELLED,
            )
            .group_by(OrderItemModel.product_variant_id)
            .order_by(func.sum(OrderItemModel.line_subtotal).desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            TopProductAgg(variant_id=r[0], units=int(r[1] or 0), revenue=_dec(r[2]))
            for r in rows
        ]

    # --- Product costing (COGS) --------------------------------------------
    async def ingredient_avg_costs(
        self, tenant_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, Decimal]]:
        # Moving-average of purchase unit prices per ingredient. Assumes the
        # purchase unit matches the recipe unit (no conversion for pilots).
        stmt = (
            select(
                PurchaseOrderItemModel.ingredient_id,
                func.avg(PurchaseOrderItemModel.unit_price),
            )
            .where(PurchaseOrderItemModel.tenant_id == tenant_id)
            .group_by(PurchaseOrderItemModel.ingredient_id)
        )
        rows = (await self._session.execute(stmt)).all()
        return [(r[0], _dec(r[1])) for r in rows]

    async def all_recipe_items(self, tenant_id: uuid.UUID) -> list[RecipeItemRow]:
        stmt = select(
            RecipeItemModel.product_variant_id,
            RecipeItemModel.ingredient_id,
            RecipeItemModel.quantity,
        ).where(RecipeItemModel.tenant_id == tenant_id)
        rows = (await self._session.execute(stmt)).all()
        return [
            RecipeItemRow(variant_id=r[0], ingredient_id=r[1], quantity=_dec(r[2]))
            for r in rows
        ]

    async def sold_items_by_channel(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[SoldItemRow]:
        stmt = (
            select(
                OrderModel.channel,
                OrderItemModel.product_variant_id,
                func.sum(OrderItemModel.quantity),
            )
            .join(OrderModel, OrderModel.id == OrderItemModel.order_id)
            .where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.branch_id == branch_id,
                OrderModel.status == _ORDER_CLOSED,
                func.date(OrderModel.closed_at).between(date_from, date_to),
                OrderItemModel.status != _ITEM_CANCELLED,
            )
            .group_by(OrderModel.channel, OrderItemModel.product_variant_id)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            SoldItemRow(channel=r[0], variant_id=r[1], units=int(r[2] or 0))
            for r in rows
        ]

    # --- Profitability (P&L, margins) --------------------------------------
    async def expenses_total(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> Decimal:
        stmt = select(func.sum(ExpenseModel.amount)).where(
            ExpenseModel.tenant_id == tenant_id,
            ExpenseModel.branch_id == branch_id,
            func.date(ExpenseModel.incurred_at).between(date_from, date_to),
        )
        return _dec((await self._session.execute(stmt)).scalar_one_or_none())

    async def labor_expenses_total(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> Decimal | None:
        # A labor category is one whose name matches a labor keyword. If the
        # tenant has no such category, labor cost is unavailable (None), not 0.
        name = func.lower(ExpenseCategoryModel.name)
        matches = or_(*(name.contains(kw) for kw in _LABOR_KEYWORDS))
        has_cat = (
            await self._session.execute(
                select(ExpenseCategoryModel.id).where(
                    ExpenseCategoryModel.tenant_id == tenant_id, matches
                )
            )
        ).first()
        if has_cat is None:
            return None
        stmt = (
            select(func.sum(ExpenseModel.amount))
            .join(
                ExpenseCategoryModel,
                ExpenseCategoryModel.id == ExpenseModel.expense_category_id,
            )
            .where(
                ExpenseModel.tenant_id == tenant_id,
                ExpenseModel.branch_id == branch_id,
                func.date(ExpenseModel.incurred_at).between(date_from, date_to),
                matches,
            )
        )
        return _dec((await self._session.execute(stmt)).scalar_one_or_none())

    async def variant_sales(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[VariantSalesRow]:
        stmt = (
            select(
                OrderItemModel.product_variant_id,
                func.sum(OrderItemModel.quantity),
                func.sum(OrderItemModel.line_subtotal),
            )
            .join(OrderModel, OrderModel.id == OrderItemModel.order_id)
            .where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.branch_id == branch_id,
                OrderModel.status == _ORDER_CLOSED,
                func.date(OrderModel.closed_at).between(date_from, date_to),
                OrderItemModel.status != _ITEM_CANCELLED,
            )
            .group_by(OrderItemModel.product_variant_id)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            VariantSalesRow(variant_id=r[0], units=int(r[1] or 0), revenue=_dec(r[2]))
            for r in rows
        ]

    # --- Cash flow (money-in / money-out) ----------------------------------
    async def cf_sales(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[MoneyFlowRow]:
        # Sales received (cash-basis): all order payments by method, on payment date.
        day = func.date(OrderPaymentModel.created_at)
        stmt = (
            select(OrderPaymentModel.method, day, func.sum(OrderPaymentModel.amount))
            .where(
                OrderPaymentModel.tenant_id == tenant_id,
                OrderPaymentModel.branch_id == branch_id,
                day.between(date_from, date_to),
            )
            .group_by(OrderPaymentModel.method, day)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            MoneyFlowRow(method=r[0], day=str(r[1])[:10], amount=_dec(r[2]))
            for r in rows
        ]

    async def cf_supplier_payments(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[MoneyFlowRow]:
        # Supplier payments are tenant-scoped; branch comes from the purchase order.
        day = func.date(PurchasePaymentModel.paid_at)
        stmt = (
            select(PurchasePaymentModel.method, day, func.sum(PurchasePaymentModel.amount))
            .join(
                PurchaseOrderModel,
                PurchaseOrderModel.id == PurchasePaymentModel.purchase_order_id,
            )
            .where(
                PurchasePaymentModel.tenant_id == tenant_id,
                PurchaseOrderModel.branch_id == branch_id,
                day.between(date_from, date_to),
            )
            .group_by(PurchasePaymentModel.method, day)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            MoneyFlowRow(method=r[0], day=str(r[1])[:10], amount=_dec(r[2]))
            for r in rows
        ]

    async def cf_expenses(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[tuple[str, Decimal]]:
        day = func.date(ExpenseModel.incurred_at)
        stmt = (
            select(day, func.sum(ExpenseModel.amount))
            .where(
                ExpenseModel.tenant_id == tenant_id,
                ExpenseModel.branch_id == branch_id,
                day.between(date_from, date_to),
            )
            .group_by(day)
        )
        rows = (await self._session.execute(stmt)).all()
        return [(str(r[0])[:10], _dec(r[1])) for r in rows]

    async def cf_movements(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
        direction: str,
    ) -> list[MovementFlowRow]:
        # Manual retiros/ingresos and cash credit abonos from the drawer ledger.
        # Exclude the mirrored concepts (sales / supplier payments) to avoid
        # double-counting them against their own tables.
        exclude = _CONCEPT_SALE if direction == _MOVEMENT_IN else _CONCEPT_PURCHASE_PAYMENT
        day = func.date(CashMovementModel.created_at)
        stmt = (
            select(
                CashMovementModel.concept,
                CashMovementModel.method,
                day,
                func.sum(CashMovementModel.amount),
            )
            .where(
                CashMovementModel.tenant_id == tenant_id,
                CashMovementModel.branch_id == branch_id,
                CashMovementModel.type == direction,
                CashMovementModel.concept != exclude,
                day.between(date_from, date_to),
            )
            .group_by(CashMovementModel.concept, CashMovementModel.method, day)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            MovementFlowRow(
                concept=r[0], method=r[1], day=str(r[2])[:10], amount=_dec(r[3])
            )
            for r in rows
        ]
