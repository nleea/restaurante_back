"""Persistence adapter for the Orders module over SQLAlchemy async.

Each write method commits its own unit of work and filters explicitly by
``tenant_id`` (and ``branch_id`` where applicable). Money fields are derived
server-side: ``recompute_item`` sets a line's subtotal from its unit price,
quantity and addons; ``recompute_totals`` sets the order subtotal/total from its
non-cancelled items and discount.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.cash.domain.entities import CashSession
from restaurante.modules.cash.infrastructure.models import (
    CashMovementModel,
    CashSessionModel,
)
from restaurante.modules.customers.infrastructure.models import CustomerModel
from restaurante.modules.inventory.infrastructure.models import (
    InventoryMovementModel,
    InventoryStockModel,
)
from restaurante.modules.menu.infrastructure.models import (
    AddonModel,
    ProductVariantModel,
)
from restaurante.modules.orders.domain.entities import (
    Cancellation,
    DiningTable,
    Order,
    OrderItem,
    OrderItemAddon,
    OrderPayment,
    ReceiptPrint,
)
from restaurante.modules.orders.infrastructure.models import (
    CancellationModel,
    DiningTableModel,
    OrderItemAddonModel,
    OrderItemModel,
    OrderModel,
    OrderPaymentModel,
    ReceiptPrintModel,
)
from restaurante.modules.recipes.infrastructure.models import RecipeItemModel
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.domain.errors import ConflictError
from restaurante.shared.tenancy.models import BranchModel

_CANCELLED = "cancelled"


def _table(m: DiningTableModel) -> DiningTable:
    return DiningTable(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        number=m.number,
        capacity=m.capacity,
        status=m.status,
        is_active=m.is_active,
    )


def _order(m: OrderModel) -> Order:
    return Order(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        channel=m.channel,
        employee_id=m.employee_id,
        status=m.status,
        subtotal=m.subtotal,
        discount=m.discount,
        total=m.total,
        kitchen_state=m.kitchen_state,
        dining_table_id=m.dining_table_id,
        customer_id=m.customer_id,
        whatsapp_contact_id=m.whatsapp_contact_id,
        closed_at=m.closed_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _item(m: OrderItemModel) -> OrderItem:
    return OrderItem(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        order_id=m.order_id,
        product_variant_id=m.product_variant_id,
        unit_price=m.unit_price,
        line_subtotal=m.line_subtotal,
        quantity=m.quantity,
        status=m.status,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _item_addon(m: OrderItemAddonModel) -> OrderItemAddon:
    return OrderItemAddon(
        id=m.id,
        tenant_id=m.tenant_id,
        order_item_id=m.order_item_id,
        addon_id=m.addon_id,
        applied_price=m.applied_price,
    )


def _cancellation(m: CancellationModel) -> Cancellation:
    return Cancellation(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        order_id=m.order_id,
        reason=m.reason,
        requires_authorization=m.requires_authorization,
        requested_by_employee_id=m.requested_by_employee_id,
        status=m.status,
        order_item_id=m.order_item_id,
        authorized_by_employee_id=m.authorized_by_employee_id,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _payment(m: OrderPaymentModel) -> OrderPayment:
    return OrderPayment(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        order_id=m.order_id,
        cash_session_id=m.cash_session_id,
        amount=m.amount,
        method=m.method,
        employee_id=m.employee_id,
        diner_reference=m.diner_reference,
        created_at=m.created_at,
    )


def _cash_session(m: CashSessionModel) -> CashSession:
    return CashSession(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        opened_by_employee_id=m.opened_by_employee_id,
        opening_amount=m.opening_amount,
        status=m.status,
        opened_at=m.opened_at,
        closed_by_employee_id=m.closed_by_employee_id,
        counted_amount=m.counted_amount,
        expected_amount=m.expected_amount,
        difference=m.difference,
        closed_at=m.closed_at,
    )


def _receipt(m: ReceiptPrintModel) -> ReceiptPrint:
    return ReceiptPrint(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        order_id=m.order_id,
        employee_id=m.employee_id,
        is_reprint=m.is_reprint,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class SqlAlchemyOrdersRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reference existence checks ----------------------------------------
    async def branch_exists(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
        stmt = select(BranchModel.id).where(
            BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def employee_exists(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool:
        stmt = select(EmployeeModel.id).where(
            EmployeeModel.id == employee_id, EmployeeModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def variant_exists(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> bool:
        stmt = select(ProductVariantModel.id).where(
            ProductVariantModel.id == product_variant_id,
            ProductVariantModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def addon_exists(self, tenant_id: uuid.UUID, addon_id: uuid.UUID) -> bool:
        stmt = select(AddonModel.id).where(
            AddonModel.id == addon_id, AddonModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Dining tables -----------------------------------------------------
    async def create_dining_table(self, table: DiningTable) -> DiningTable:
        model = DiningTableModel(
            tenant_id=table.tenant_id,
            branch_id=table.branch_id,
            number=table.number,
            capacity=table.capacity,
            status=table.status,
            is_active=table.is_active,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(
                "Ya existe una mesa con ese número en la sucursal."
            ) from exc
        await self._session.refresh(model)
        return _table(model)

    async def _get_table_model(
        self, tenant_id: uuid.UUID, table_id: uuid.UUID
    ) -> DiningTableModel | None:
        stmt = select(DiningTableModel).where(
            DiningTableModel.id == table_id, DiningTableModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_dining_table(
        self, tenant_id: uuid.UUID, table_id: uuid.UUID
    ) -> DiningTable | None:
        model = await self._get_table_model(tenant_id, table_id)
        return _table(model) if model else None

    async def list_dining_tables(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[DiningTable]:
        stmt = (
            select(DiningTableModel)
            .where(
                DiningTableModel.tenant_id == tenant_id,
                DiningTableModel.branch_id == branch_id,
            )
            .order_by(DiningTableModel.number)
        )
        return [_table(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_dining_table(
        self, tenant_id: uuid.UUID, table_id: uuid.UUID, fields: dict[str, Any]
    ) -> DiningTable | None:
        model = await self._get_table_model(tenant_id, table_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _table(model)

    # --- Orders ------------------------------------------------------------
    async def create_order(self, order: Order) -> Order:
        model = OrderModel(
            tenant_id=order.tenant_id,
            branch_id=order.branch_id,
            channel=order.channel,
            employee_id=order.employee_id,
            status=order.status,
            subtotal=order.subtotal,
            discount=order.discount,
            total=order.total,
            dining_table_id=order.dining_table_id,
            customer_id=order.customer_id,
            whatsapp_contact_id=order.whatsapp_contact_id,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _order(model)

    async def _get_order_model(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderModel | None:
        stmt = select(OrderModel).where(
            OrderModel.id == order_id, OrderModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Order | None:
        model = await self._get_order_model(tenant_id, order_id)
        return _order(model) if model else None

    async def list_orders(
        self,
        tenant_id: uuid.UUID,
        *,
        branch_id: uuid.UUID | None = None,
        status: str | None = None,
        dining_table_id: uuid.UUID | None = None,
    ) -> list[Order]:
        stmt = select(OrderModel).where(OrderModel.tenant_id == tenant_id)
        if branch_id is not None:
            stmt = stmt.where(OrderModel.branch_id == branch_id)
        if status is not None:
            stmt = stmt.where(OrderModel.status == status)
        if dining_table_id is not None:
            stmt = stmt.where(OrderModel.dining_table_id == dining_table_id)
        stmt = stmt.order_by(OrderModel.created_at.desc())
        return [_order(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, fields: dict[str, Any]
    ) -> Order | None:
        model = await self._get_order_model(tenant_id, order_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _order(model)

    async def close_order(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        *,
        status: str,
        closed_at: datetime,
        customer_id: uuid.UUID | None,
        total: Decimal,
    ) -> Order | None:
        """Flip the order to closed and, when a customer is linked, bump that customer's purchase
        stats atomically in the same commit. The increment is a SQL column expression (safe under
        concurrency); exactly-once is guaranteed by the caller's open-status guard."""
        model = await self._get_order_model(tenant_id, order_id)
        if model is None:
            return None
        model.status = status
        model.closed_at = closed_at
        if customer_id is not None:
            await self._session.execute(
                update(CustomerModel)
                .where(
                    CustomerModel.id == customer_id,
                    CustomerModel.tenant_id == tenant_id,
                )
                .values(
                    total_spent=CustomerModel.total_spent + total,
                    order_count=CustomerModel.order_count + 1,
                    last_purchase_at=closed_at,
                )
            )
        await self._session.commit()
        await self._session.refresh(model)
        return _order(model)

    async def recompute_totals(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Order:
        model = await self._get_order_model(tenant_id, order_id)
        if model is None:
            raise ConflictError(f"Orden no encontrada: {order_id}")
        subtotal_stmt = select(
            func.coalesce(func.sum(OrderItemModel.line_subtotal), 0)
        ).where(
            OrderItemModel.tenant_id == tenant_id,
            OrderItemModel.order_id == order_id,
            OrderItemModel.status != _CANCELLED,
        )
        subtotal = Decimal(
            str((await self._session.execute(subtotal_stmt)).scalar_one())
        )
        model.subtotal = subtotal
        model.total = subtotal - model.discount
        await self._session.commit()
        await self._session.refresh(model)
        return _order(model)

    # --- Order items -------------------------------------------------------
    async def create_item(self, item: OrderItem) -> OrderItem:
        model = OrderItemModel(
            tenant_id=item.tenant_id,
            branch_id=item.branch_id,
            order_id=item.order_id,
            product_variant_id=item.product_variant_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_subtotal=item.line_subtotal,
            status=item.status,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _item(model)

    async def _get_item_model(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> OrderItemModel | None:
        stmt = select(OrderItemModel).where(
            OrderItemModel.id == item_id, OrderItemModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> OrderItem | None:
        model = await self._get_item_model(tenant_id, item_id)
        return _item(model) if model else None

    async def list_items(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[OrderItem]:
        stmt = (
            select(OrderItemModel)
            .where(
                OrderItemModel.tenant_id == tenant_id,
                OrderItemModel.order_id == order_id,
            )
            .order_by(OrderItemModel.created_at)
        )
        return [_item(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderItem | None:
        model = await self._get_item_model(tenant_id, item_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _item(model)

    async def _addons_sum(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> Decimal:
        stmt = select(
            func.coalesce(func.sum(OrderItemAddonModel.applied_price), 0)
        ).where(
            OrderItemAddonModel.tenant_id == tenant_id,
            OrderItemAddonModel.order_item_id == item_id,
        )
        return Decimal(str((await self._session.execute(stmt)).scalar_one()))

    async def recompute_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> OrderItem | None:
        model = await self._get_item_model(tenant_id, item_id)
        if model is None:
            return None
        addons = await self._addons_sum(tenant_id, item_id)
        model.line_subtotal = model.unit_price * model.quantity + addons
        await self._session.commit()
        await self._session.refresh(model)
        return _item(model)

    async def delete_item(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> None:
        await self._session.execute(
            sql_delete(OrderItemModel).where(
                OrderItemModel.tenant_id == tenant_id, OrderItemModel.id == item_id
            )
        )
        await self._session.commit()

    # --- Item addons -------------------------------------------------------
    async def create_item_addon(self, addon: OrderItemAddon) -> OrderItemAddon:
        model = OrderItemAddonModel(
            tenant_id=addon.tenant_id,
            order_item_id=addon.order_item_id,
            addon_id=addon.addon_id,
            applied_price=addon.applied_price,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _item_addon(model)

    async def get_item_addon(
        self, tenant_id: uuid.UUID, item_addon_id: uuid.UUID
    ) -> OrderItemAddon | None:
        stmt = select(OrderItemAddonModel).where(
            OrderItemAddonModel.id == item_addon_id,
            OrderItemAddonModel.tenant_id == tenant_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _item_addon(model) if model else None

    async def list_item_addons(
        self, tenant_id: uuid.UUID, order_item_id: uuid.UUID
    ) -> list[OrderItemAddon]:
        stmt = select(OrderItemAddonModel).where(
            OrderItemAddonModel.tenant_id == tenant_id,
            OrderItemAddonModel.order_item_id == order_item_id,
        )
        return [_item_addon(m) for m in (await self._session.execute(stmt)).scalars()]

    async def delete_item_addon(
        self, tenant_id: uuid.UUID, item_addon_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            sql_delete(OrderItemAddonModel).where(
                OrderItemAddonModel.tenant_id == tenant_id,
                OrderItemAddonModel.id == item_addon_id,
            )
        )
        await self._session.commit()

    # --- Cancellations / receipts -----------------------------------------
    async def create_cancellation(self, cancellation: Cancellation) -> Cancellation:
        model = CancellationModel(
            tenant_id=cancellation.tenant_id,
            branch_id=cancellation.branch_id,
            order_id=cancellation.order_id,
            order_item_id=cancellation.order_item_id,
            reason=cancellation.reason,
            requires_authorization=cancellation.requires_authorization,
            requested_by_employee_id=cancellation.requested_by_employee_id,
            authorized_by_employee_id=cancellation.authorized_by_employee_id,
            status=cancellation.status,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _cancellation(model)

    async def create_receipt_print(self, receipt: ReceiptPrint) -> ReceiptPrint:
        model = ReceiptPrintModel(
            tenant_id=receipt.tenant_id,
            branch_id=receipt.branch_id,
            order_id=receipt.order_id,
            employee_id=receipt.employee_id,
            is_reprint=receipt.is_reprint,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _receipt(model)

    async def order_has_receipt(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> bool:
        stmt = select(ReceiptPrintModel.id).where(
            ReceiptPrintModel.tenant_id == tenant_id,
            ReceiptPrintModel.order_id == order_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Payments (orders ↔ cash integration) ------------------------------
    async def get_open_cash_session(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> CashSession | None:
        stmt = select(CashSessionModel).where(
            CashSessionModel.tenant_id == tenant_id,
            CashSessionModel.branch_id == branch_id,
            CashSessionModel.status == "open",
        )
        model = (await self._session.execute(stmt)).scalars().first()
        return _cash_session(model) if model else None

    async def register_payment(self, payment: OrderPayment) -> OrderPayment:
        """Persist the order payment and the matching `sale` cash movement atomically."""
        payment_model = OrderPaymentModel(
            tenant_id=payment.tenant_id,
            branch_id=payment.branch_id,
            order_id=payment.order_id,
            cash_session_id=payment.cash_session_id,
            amount=payment.amount,
            method=payment.method,
            diner_reference=payment.diner_reference,
            employee_id=payment.employee_id,
        )
        movement_model = CashMovementModel(
            tenant_id=payment.tenant_id,
            branch_id=payment.branch_id,
            cash_session_id=payment.cash_session_id,
            type="in",
            concept="sale",
            amount=payment.amount,
            method=payment.method,
            reference_id=payment.order_id,
        )
        self._session.add(payment_model)
        self._session.add(movement_model)
        await self._session.commit()
        await self._session.refresh(payment_model)
        return _payment(payment_model)

    async def list_payments(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[OrderPayment]:
        stmt = (
            select(OrderPaymentModel)
            .where(
                OrderPaymentModel.tenant_id == tenant_id,
                OrderPaymentModel.order_id == order_id,
            )
            .order_by(OrderPaymentModel.created_at)
        )
        return [_payment(m) for m in (await self._session.execute(stmt)).scalars()]

    # --- Inventory deduction (orders ↔ recipes ↔ inventory) ----------------
    async def consume_inventory_for_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> None:
        """Deduct each non-cancelled item's recipe ingredients from stock.

        Idempotent (skips if `sale` movements already exist for the order),
        non-blocking (stock may go negative), and atomic (single commit).
        """
        already = (
            await self._session.execute(
                select(InventoryMovementModel.id).where(
                    InventoryMovementModel.tenant_id == tenant_id,
                    InventoryMovementModel.reference_id == order_id,
                    InventoryMovementModel.reason == "sale",
                )
            )
        ).first()
        if already is not None:
            return

        order = await self._get_order_model(tenant_id, order_id)
        if order is None:
            return

        items = (
            await self._session.execute(
                select(OrderItemModel).where(
                    OrderItemModel.tenant_id == tenant_id,
                    OrderItemModel.order_id == order_id,
                    OrderItemModel.status != _CANCELLED,
                )
            )
        ).scalars().all()

        for item in items:
            recipe_items = (
                await self._session.execute(
                    select(RecipeItemModel).where(
                        RecipeItemModel.tenant_id == tenant_id,
                        RecipeItemModel.product_variant_id == item.product_variant_id,
                    )
                )
            ).scalars().all()
            for line in recipe_items:
                consumed = line.quantity * item.quantity
                stock = (
                    await self._session.execute(
                        select(InventoryStockModel).where(
                            InventoryStockModel.tenant_id == tenant_id,
                            InventoryStockModel.branch_id == order.branch_id,
                            InventoryStockModel.ingredient_id == line.ingredient_id,
                        )
                    )
                ).scalar_one_or_none()
                if stock is None:
                    stock = InventoryStockModel(
                        tenant_id=tenant_id,
                        branch_id=order.branch_id,
                        ingredient_id=line.ingredient_id,
                        current_quantity=-consumed,
                        min_stock=Decimal(0),
                    )
                    self._session.add(stock)
                else:
                    stock.current_quantity = stock.current_quantity - consumed
                self._session.add(
                    InventoryMovementModel(
                        tenant_id=tenant_id,
                        branch_id=order.branch_id,
                        ingredient_id=line.ingredient_id,
                        type="out",
                        reason="sale",
                        quantity=consumed,
                        employee_id=order.employee_id,
                        reference_id=order_id,
                    )
                )

        await self._session.commit()
