"""Ports (interfaces) of the Orders module."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from restaurante.modules.cash.domain.entities import CashSession
from restaurante.modules.orders.domain.entities import (
    Cancellation,
    DiningTable,
    Order,
    OrderItem,
    OrderItemAddon,
    OrderPayment,
    ReceiptPrint,
)


class KitchenRouting(Protocol):
    """Outbound port: route an order to the kitchen (create KDS tickets for routable items).

    Kept here so the orders application depends on an interface, not the kitchen module — the
    concrete adapter is wired at the composition root, preserving a one-way module dependency.
    """

    async def route_order(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> None: ...


class DeliveryDispatch(Protocol):
    """Outbound port: ensure a `delivery` order has its delivery record (Dispatch entry).

    Kept here so the orders application depends on an interface, not the delivery module — the
    concrete adapter is wired at the composition root. The implementation MUST be idempotent
    (do nothing if the order already has a delivery record).
    """

    async def ensure_delivery_for_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> None: ...


class OrdersRepository(Protocol):
    # --- Reference existence checks ----------------------------------------
    async def branch_exists(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool: ...

    async def employee_exists(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool: ...

    async def variant_exists(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> bool: ...

    async def addon_exists(
        self, tenant_id: uuid.UUID, addon_id: uuid.UUID
    ) -> bool: ...

    # --- Dining tables -----------------------------------------------------
    async def create_dining_table(self, table: DiningTable) -> DiningTable: ...

    async def get_dining_table(
        self, tenant_id: uuid.UUID, table_id: uuid.UUID
    ) -> DiningTable | None: ...

    async def list_dining_tables(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[DiningTable]: ...

    async def update_dining_table(
        self, tenant_id: uuid.UUID, table_id: uuid.UUID, fields: dict[str, Any]
    ) -> DiningTable | None: ...

    # --- Orders ------------------------------------------------------------
    async def create_order(self, order: Order) -> Order: ...

    async def get_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Order | None: ...

    async def list_orders(
        self,
        tenant_id: uuid.UUID,
        *,
        branch_id: uuid.UUID | None = None,
        status: str | None = None,
        dining_table_id: uuid.UUID | None = None,
    ) -> list[Order]: ...

    async def update_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, fields: dict[str, Any]
    ) -> Order | None: ...

    async def close_order(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        *,
        status: str,
        closed_at: datetime,
        customer_id: uuid.UUID | None,
        total: Decimal,
    ) -> Order | None: ...

    async def recompute_totals(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Order: ...

    # --- Order items -------------------------------------------------------
    async def create_item(self, item: OrderItem) -> OrderItem: ...

    async def get_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> OrderItem | None: ...

    async def list_items(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[OrderItem]: ...

    async def update_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderItem | None: ...

    async def recompute_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> OrderItem | None: ...

    async def delete_item(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> None: ...

    # --- Item addons -------------------------------------------------------
    async def create_item_addon(self, addon: OrderItemAddon) -> OrderItemAddon: ...

    async def get_item_addon(
        self, tenant_id: uuid.UUID, item_addon_id: uuid.UUID
    ) -> OrderItemAddon | None: ...

    async def list_item_addons(
        self, tenant_id: uuid.UUID, order_item_id: uuid.UUID
    ) -> list[OrderItemAddon]: ...

    async def delete_item_addon(
        self, tenant_id: uuid.UUID, item_addon_id: uuid.UUID
    ) -> None: ...

    # --- Cancellations / receipts -----------------------------------------
    async def create_cancellation(
        self, cancellation: Cancellation
    ) -> Cancellation: ...

    async def create_receipt_print(self, receipt: ReceiptPrint) -> ReceiptPrint: ...

    async def order_has_receipt(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> bool: ...

    # --- Payments (orders ↔ cash integration) ------------------------------
    async def get_open_cash_session(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> CashSession | None: ...

    async def register_payment(self, payment: OrderPayment) -> OrderPayment: ...

    async def list_payments(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[OrderPayment]: ...

    # --- Inventory deduction (orders ↔ recipes ↔ inventory) ----------------
    async def consume_inventory_for_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> None: ...
