"""Application service for the Orders module (operational core).

Owns the order lifecycle: dining tables, opening orders, items, addons, totals,
discounts, cancellations, close and receipt prints. Money fields are recomputed
server-side; status guards enforce the state machine. Payments and inventory
deduction are out of scope for this module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from restaurante.modules.orders.domain.entities import (
    Cancellation,
    DiningTable,
    Order,
    OrderItem,
    OrderItemAddon,
    ReceiptPrint,
)
from restaurante.modules.orders.domain.ports import (
    DeliveryDispatch,
    KitchenRouting,
    OrdersRepository,
)
from restaurante.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

CHANNELS = ("dine_in", "takeaway", "delivery")
CHANNEL_DELIVERY = "delivery"

ORDER_OPEN = "open"
ORDER_CLOSED = "closed"
ORDER_CANCELLED = "cancelled"

ITEM_CANCELLED = "cancelled"

TABLE_FREE = "free"
TABLE_OCCUPIED = "occupied"

KITCHEN_STATE_READY = "ready"


class OrderService:
    def __init__(
        self,
        repo: OrdersRepository,
        kitchen_routing: KitchenRouting | None = None,
        delivery_dispatch: DeliveryDispatch | None = None,
    ) -> None:
        self._repo = repo
        # Optional outbound port: when wired, adding an item auto-routes the order to the kitchen.
        self._kitchen_routing = kitchen_routing
        # Optional outbound port: when wired, a ready delivery order auto-creates its dispatch
        # (delivery) record so it enters Dispatch as pending.
        self._delivery_dispatch = delivery_dispatch

    # --- internal guards ---------------------------------------------------
    async def _require_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> None:
        if not await self._repo.branch_exists(tenant_id, branch_id):
            raise NotFoundError(f"Sucursal no encontrada: {branch_id}")

    async def _require_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> None:
        if not await self._repo.employee_exists(tenant_id, employee_id):
            raise NotFoundError(f"Empleado no encontrado: {employee_id}")

    async def _require_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Order:
        order = await self._repo.get_order(tenant_id, order_id)
        if order is None:
            raise NotFoundError(f"Orden no encontrada: {order_id}")
        return order

    async def _require_open_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Order:
        order = await self._require_order(tenant_id, order_id)
        if order.status != ORDER_OPEN:
            raise ConflictError(
                f"La orden no está abierta (estado: {order.status})."
            )
        return order

    async def _require_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> OrderItem:
        item = await self._repo.get_item(tenant_id, item_id)
        if item is None:
            raise NotFoundError(f"Ítem de orden no encontrado: {item_id}")
        return item

    async def _free_table(self, tenant_id: uuid.UUID, order: Order) -> None:
        if order.dining_table_id is not None:
            await self._repo.update_dining_table(
                tenant_id, order.dining_table_id, {"status": TABLE_FREE}
            )

    # --- Dining tables -----------------------------------------------------
    async def create_dining_table(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        number: str,
        capacity: int,
    ) -> DiningTable:
        await self._require_branch(tenant_id, branch_id)
        if capacity <= 0:
            raise ValidationError("La capacidad debe ser positiva.")
        return await self._repo.create_dining_table(
            DiningTable(
                tenant_id=tenant_id,
                branch_id=branch_id,
                number=number,
                capacity=capacity,
            )
        )

    async def list_dining_tables(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[DiningTable]:
        await self._require_branch(tenant_id, branch_id)
        return await self._repo.list_dining_tables(tenant_id, branch_id)

    async def update_dining_table(
        self, tenant_id: uuid.UUID, table_id: uuid.UUID, fields: dict[str, Any]
    ) -> DiningTable:
        if "capacity" in fields and fields["capacity"] is not None:
            if fields["capacity"] <= 0:
                raise ValidationError("La capacidad debe ser positiva.")
        updated = await self._repo.update_dining_table(tenant_id, table_id, fields)
        if updated is None:
            raise NotFoundError(f"Mesa no encontrada: {table_id}")
        return updated

    # --- Orders ------------------------------------------------------------
    async def open_order(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        channel: str,
        employee_id: uuid.UUID,
        dining_table_id: uuid.UUID | None = None,
        customer_id: uuid.UUID | None = None,
        whatsapp_contact_id: uuid.UUID | None = None,
    ) -> Order:
        if channel not in CHANNELS:
            raise ValidationError(f"Canal inválido: {channel}")
        await self._require_branch(tenant_id, branch_id)
        await self._require_employee(tenant_id, employee_id)
        if dining_table_id is not None:
            table = await self._repo.get_dining_table(tenant_id, dining_table_id)
            if table is None or table.branch_id != branch_id:
                raise NotFoundError(
                    f"Mesa no encontrada en la sucursal: {dining_table_id}"
                )
        order = await self._repo.create_order(
            Order(
                tenant_id=tenant_id,
                branch_id=branch_id,
                channel=channel,
                employee_id=employee_id,
                dining_table_id=dining_table_id,
                customer_id=customer_id,
                whatsapp_contact_id=whatsapp_contact_id,
            )
        )
        if dining_table_id is not None:
            await self._repo.update_dining_table(
                tenant_id, dining_table_id, {"status": TABLE_OCCUPIED}
            )
        return order

    async def get_order(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> Order:
        return await self._require_order(tenant_id, order_id)

    async def get_order_items(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[OrderItem]:
        await self._require_order(tenant_id, order_id)
        return await self._repo.list_items(tenant_id, order_id)

    async def list_item_addons(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> list[OrderItemAddon]:
        await self._require_item(tenant_id, item_id)
        return await self._repo.list_item_addons(tenant_id, item_id)

    async def list_orders(
        self,
        tenant_id: uuid.UUID,
        *,
        branch_id: uuid.UUID | None = None,
        status: str | None = None,
        dining_table_id: uuid.UUID | None = None,
    ) -> list[Order]:
        return await self._repo.list_orders(
            tenant_id,
            branch_id=branch_id,
            status=status,
            dining_table_id=dining_table_id,
        )

    async def set_kitchen_state(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, state: str
    ) -> Order | None:
        """Persist an order's derived kitchen readiness (pushed by the kitchen side).

        When the order reaches `ready` on the `delivery` channel, auto-create its delivery record
        so it enters Dispatch as `pending`. That creation is idempotent and a non-blocking side
        effect: a delivery-create failure must not fail the readiness update or the ticket advance.
        """
        order = await self._repo.get_order(tenant_id, order_id)
        if order is None:
            return None
        updated = await self._repo.update_order(
            tenant_id, order_id, {"kitchen_state": state}
        )
        if (
            state == KITCHEN_STATE_READY
            and order.channel == CHANNEL_DELIVERY
            and self._delivery_dispatch is not None
        ):
            try:
                await self._delivery_dispatch.ensure_delivery_for_order(
                    tenant_id, order_id
                )
            except Exception:  # noqa: BLE001 - dispatch create is a non-blocking side effect
                pass
        return updated

    # --- Items -------------------------------------------------------------
    async def add_item(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        product_variant_id: uuid.UUID,
        quantity: int,
        unit_price: Decimal,
    ) -> OrderItem:
        order = await self._require_open_order(tenant_id, order_id)
        if not await self._repo.variant_exists(tenant_id, product_variant_id):
            raise NotFoundError(
                f"Variante de producto no encontrada: {product_variant_id}"
            )
        if quantity <= 0:
            raise ValidationError("La cantidad debe ser positiva.")
        item = await self._repo.create_item(
            OrderItem(
                tenant_id=tenant_id,
                branch_id=order.branch_id,
                order_id=order_id,
                product_variant_id=product_variant_id,
                unit_price=unit_price,
                line_subtotal=unit_price * quantity,
                quantity=quantity,
            )
        )
        await self._repo.recompute_totals(tenant_id, order_id)
        # Auto-route the order to the kitchen so the new item appears on the KDS without a manual
        # step. Best-effort and non-blocking: a routing failure must not fail the item add. The
        # routing is idempotent and a no-op when no station mappings exist.
        if self._kitchen_routing is not None:
            try:
                await self._kitchen_routing.route_order(tenant_id, order_id)
            except Exception:  # noqa: BLE001 - kitchen routing is a non-blocking side effect
                pass
        return item

    async def update_item_quantity(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID, quantity: int
    ) -> OrderItem:
        item = await self._require_item(tenant_id, item_id)
        await self._require_open_order(tenant_id, item.order_id)
        if quantity <= 0:
            raise ValidationError("La cantidad debe ser positiva.")
        await self._repo.update_item(tenant_id, item_id, {"quantity": quantity})
        updated = await self._repo.recompute_item(tenant_id, item_id)
        await self._repo.recompute_totals(tenant_id, item.order_id)
        assert updated is not None
        return updated

    async def remove_item(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> None:
        item = await self._require_item(tenant_id, item_id)
        await self._require_open_order(tenant_id, item.order_id)
        await self._repo.delete_item(tenant_id, item_id)
        await self._repo.recompute_totals(tenant_id, item.order_id)

    # --- Addons ------------------------------------------------------------
    async def attach_addon(
        self,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        addon_id: uuid.UUID,
        applied_price: Decimal,
    ) -> OrderItemAddon:
        item = await self._require_item(tenant_id, item_id)
        await self._require_open_order(tenant_id, item.order_id)
        if not await self._repo.addon_exists(tenant_id, addon_id):
            raise NotFoundError(f"Adición no encontrada: {addon_id}")
        addon = await self._repo.create_item_addon(
            OrderItemAddon(
                tenant_id=tenant_id,
                order_item_id=item_id,
                addon_id=addon_id,
                applied_price=applied_price,
            )
        )
        await self._repo.recompute_item(tenant_id, item_id)
        await self._repo.recompute_totals(tenant_id, item.order_id)
        return addon

    async def detach_addon(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID, item_addon_id: uuid.UUID
    ) -> None:
        item = await self._require_item(tenant_id, item_id)
        await self._require_open_order(tenant_id, item.order_id)
        existing = await self._repo.get_item_addon(tenant_id, item_addon_id)
        if existing is None or existing.order_item_id != item_id:
            raise NotFoundError(f"Adición de ítem no encontrada: {item_addon_id}")
        await self._repo.delete_item_addon(tenant_id, item_addon_id)
        await self._repo.recompute_item(tenant_id, item_id)
        await self._repo.recompute_totals(tenant_id, item.order_id)

    # --- Discount ----------------------------------------------------------
    async def set_discount(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, discount: Decimal
    ) -> Order:
        order = await self._require_open_order(tenant_id, order_id)
        if discount < 0 or discount > order.subtotal:
            raise ValidationError(
                "El descuento debe estar entre 0 y el subtotal de la orden."
            )
        await self._repo.update_order(tenant_id, order_id, {"discount": discount})
        return await self._repo.recompute_totals(tenant_id, order_id)

    # --- Cancellations -----------------------------------------------------
    async def cancel_item(
        self,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        reason: str,
        requested_by_employee_id: uuid.UUID,
        requires_authorization: bool = False,
        authorized_by_employee_id: uuid.UUID | None = None,
    ) -> None:
        item = await self._require_item(tenant_id, item_id)
        order = await self._require_open_order(tenant_id, item.order_id)
        await self._require_employee(tenant_id, requested_by_employee_id)
        await self._repo.create_cancellation(
            Cancellation(
                tenant_id=tenant_id,
                branch_id=order.branch_id,
                order_id=item.order_id,
                order_item_id=item_id,
                reason=reason,
                requires_authorization=requires_authorization,
                requested_by_employee_id=requested_by_employee_id,
                authorized_by_employee_id=authorized_by_employee_id,
            )
        )
        await self._repo.update_item(tenant_id, item_id, {"status": ITEM_CANCELLED})
        await self._repo.recompute_totals(tenant_id, item.order_id)

    async def cancel_order(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        reason: str,
        requested_by_employee_id: uuid.UUID,
        requires_authorization: bool = False,
        authorized_by_employee_id: uuid.UUID | None = None,
    ) -> Order:
        order = await self._require_open_order(tenant_id, order_id)
        await self._require_employee(tenant_id, requested_by_employee_id)
        await self._repo.create_cancellation(
            Cancellation(
                tenant_id=tenant_id,
                branch_id=order.branch_id,
                order_id=order_id,
                reason=reason,
                requires_authorization=requires_authorization,
                requested_by_employee_id=requested_by_employee_id,
                authorized_by_employee_id=authorized_by_employee_id,
            )
        )
        updated = await self._repo.update_order(
            tenant_id, order_id, {"status": ORDER_CANCELLED}
        )
        await self._free_table(tenant_id, order)
        assert updated is not None
        return updated

    # --- Close / receipts --------------------------------------------------
    async def close_order(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> Order:
        order = await self._require_open_order(tenant_id, order_id)
        # Deduct ingredients via recipes before marking the order closed. The
        # deduction is idempotent and non-blocking (stock may go negative).
        await self._repo.consume_inventory_for_order(tenant_id, order_id)
        # Close and, when the order has a linked customer, bump that customer's purchase stats
        # (order_count, total_spent, last_purchase_at) atomically with the status flip.
        updated = await self._repo.close_order(
            tenant_id,
            order_id,
            status=ORDER_CLOSED,
            closed_at=datetime.now(UTC),
            customer_id=order.customer_id,
            total=order.total,
        )
        await self._free_table(tenant_id, order)
        assert updated is not None
        return updated

    async def record_receipt_print(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, employee_id: uuid.UUID
    ) -> ReceiptPrint:
        order = await self._require_order(tenant_id, order_id)
        await self._require_employee(tenant_id, employee_id)
        is_reprint = await self._repo.order_has_receipt(tenant_id, order_id)
        return await self._repo.create_receipt_print(
            ReceiptPrint(
                tenant_id=tenant_id,
                branch_id=order.branch_id,
                order_id=order_id,
                employee_id=employee_id,
                is_reprint=is_reprint,
            )
        )
