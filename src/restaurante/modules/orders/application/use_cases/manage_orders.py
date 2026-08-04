"""Application service for the Orders module (operational core).

Owns the order lifecycle: dining tables, opening orders, items, addons, totals,
discounts, cancellations, close and receipt prints. Money fields are recomputed
server-side; status guards enforce the state machine. Payments and inventory
deduction are out of scope for this module.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
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
from restaurante.shared.customer_channel.ports import (
    CUSTOMER_STATE_CANCELLED,
    CUSTOMER_STATE_READY,
    CustomerNotifier,
)
from restaurante.shared.domain.errors import (
    CashClosedError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from restaurante.shared.realtime.ports import EventPublisher

# Live-board topic for the Salón surface (floor: tables + orders).
EVENT_TOPIC = "orders"

CHANNELS = ("dine_in", "takeaway", "delivery")
CHANNEL_DELIVERY = "delivery"

logger = logging.getLogger(__name__)

ORDER_OPEN = "open"
ORDER_CLOSED = "closed"
ORDER_CANCELLED = "cancelled"

ITEM_CANCELLED = "cancelled"

TABLE_FREE = "free"
TABLE_OCCUPIED = "occupied"

KITCHEN_STATE_READY = "ready"

# --- El enlace con el que el cliente edita su propio pedido -------------------------------
#
# 24 bytes de aleatoriedad real. El token es una CAPACIDAD: quien lo tenga edita ese pedido,
# así que adivinarlo tiene que ser imposible, no improbable.
_EDIT_TOKEN_BYTES = 24
# Cuánto vive. Un pedido se resuelve el mismo día; más allá de eso el enlace es un cabo suelto
# circulando por un chat que ya nadie mira.
EDIT_TOKEN_HOURS = 12


def _as_utc(value: datetime) -> datetime:
    """SQLite devuelve los instantes sin zona; Postgres con ella."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class OrderService:
    def __init__(
        self,
        repo: OrdersRepository,
        kitchen_routing: KitchenRouting | None = None,
        delivery_dispatch: DeliveryDispatch | None = None,
        events: EventPublisher | None = None,
        customer_notifier: CustomerNotifier | None = None,
    ) -> None:
        self._repo = repo
        # Optional outbound port: when wired, adding an item auto-routes the order to the kitchen.
        self._kitchen_routing = kitchen_routing
        # Optional outbound port: when wired, a ready delivery order auto-creates its dispatch
        # (delivery) record so it enters Dispatch as pending.
        self._delivery_dispatch = delivery_dispatch
        # Optional live-board publisher (best-effort doorbell). Absent → today's behaviour
        # exactly; a broker outage never fails an order/table mutation.
        self._events = events
        # Puerto opcional hacia el canal del cliente (WhatsApp). Ausente → nadie recibe
        # nada, que es exactamente como se comportaba esto antes de que existiera.
        self._customer_notifier = customer_notifier

    async def _notify_customer(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, state: str
    ) -> None:
        """Aviso al cliente, best-effort por partida doble.

        El puerto ya promete no levantar; aquí se traga igual. Cancelar una comanda no
        puede fallar porque WhatsApp esté caído."""
        if self._customer_notifier is None:
            return
        try:
            await self._customer_notifier.notify_order_state(tenant_id, order_id, state)
        except Exception:  # noqa: BLE001 - avisar al cliente es un efecto secundario
            pass

    async def _publish(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, kind: str
    ) -> None:
        """Best-effort branch-scoped notification that the Salón changed.

        A thin doorbell: the floor refetches tables/orders on receipt. A publish failure must
        never fail the mutation, so it is swallowed here on top of the port's best-effort
        contract (mirrors the KDS `_publish_event`)."""
        if self._events is None:
            return
        try:
            await self._events.publish(
                EVENT_TOPIC,
                tenant_id,
                branch_id,
                {"kind": kind, "branch_id": str(branch_id)},
            )
        except Exception:  # noqa: BLE001 - board push is a non-blocking side effect
            pass

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

    async def _release_delivery(self, tenant_id: uuid.UUID, order: Order) -> None:
        """Suelta la entrega de una comanda que deja de existir. El gemelo de `_free_table`.

        Se traga los fallos porque no poder soltar la entrega no puede impedir cancelar una
        comanda equivocada — pero se REGISTRA, y esa es la diferencia con tragar en silencio: un
        fallo aquí devuelve exactamente el bug que esto arregla (una entrega que bloquea la caja
        del turno sin causa visible), así que tiene que quedar dicho dónde mirar.
        """
        if order.channel != CHANNEL_DELIVERY or self._delivery_dispatch is None:
            return
        if order.id is None:  # pragma: no cover - las órdenes leídas siempre lo tienen
            return
        try:
            await self._delivery_dispatch.release_delivery_for_order(tenant_id, order.id)
        except Exception:  # noqa: BLE001 - soltar la entrega no puede costar la cancelación
            logger.warning(
                "No se pudo soltar la entrega de la comanda %s; puede quedar bloqueando "
                "el cierre de su caja.",
                order.id,
                exc_info=True,
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
        table = await self._repo.create_dining_table(
            DiningTable(
                tenant_id=tenant_id,
                branch_id=branch_id,
                number=number,
                capacity=capacity,
            )
        )
        await self._publish(tenant_id, branch_id, "table")
        return table

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
        await self._publish(tenant_id, updated.branch_id, "table")
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
        payment_method: str | None = None,
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
        # The open cash session IS the operating shift: no open caja → no orders, on every
        # channel (this is the single creation choke point). Stamp the order with it so
        # deliveries/kitchen inherit the shift and the live boards can scope to it.
        session = await self._repo.get_open_cash_session(tenant_id, branch_id)
        if session is None:
            raise CashClosedError(
                "La caja está cerrada: abra la caja para recibir pedidos."
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
                payment_method=payment_method,
                cash_session_id=session.id,
            )
        )
        if dining_table_id is not None:
            await self._repo.update_dining_table(
                tenant_id, dining_table_id, {"status": TABLE_OCCUPIED}
            )
        await self._publish(tenant_id, branch_id, "created")
        return order

    # --- El enlace de edición ------------------------------------------------
    async def mint_edit_token(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> tuple[str, datetime]:
        """Acuña el token con el que el cliente abrirá SU pedido.

        Siempre uno nuevo: se acuña al crear el pedido y no se renueva sola. Un token que se
        renovara al abrirlo mantendría vivo para siempre un enlace reenviado.
        """
        token = secrets.token_urlsafe(_EDIT_TOKEN_BYTES)
        expires = datetime.now(UTC) + timedelta(hours=EDIT_TOKEN_HOURS)
        await self._repo.set_edit_token(tenant_id, order_id, token, expires)
        return token, expires

    async def order_for_edit_token(
        self, tenant_id: uuid.UUID, token: str
    ) -> Order | None:
        """El pedido detrás del token, o `None`.

        Un solo `None` para las cuatro formas de fallar —vencido, desconocido, de otro tenant,
        de otro pedido—. Distinguirlas convertiría el endpoint en un oráculo: con respuestas
        distintas, probar tokens diría qué pedidos existen.
        """
        order = await self._repo.get_order_by_edit_token(token)
        if order is None or order.tenant_id != tenant_id:
            return None
        expires = order.edit_token_expires_at
        if expires is None or _as_utc(expires) <= datetime.now(UTC):
            return None
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
        open_session_only: bool = False,
        # Filtro por contacto de WhatsApp: es lo que permite a un cliente preguntar por SU
        # pedido sin identificarse con nada más que el número desde el que ya escribió. Va
        # aquí y no en una consulta aparte para que la respuesta salga por el mismo camino
        # —mismo tenant, mismas reglas— que el resto del módulo.
        whatsapp_contact_id: uuid.UUID | None = None,
    ) -> list[Order]:
        return await self._repo.list_orders(
            tenant_id,
            branch_id=branch_id,
            status=status,
            dining_table_id=dining_table_id,
            open_session_only=open_session_only,
            whatsapp_contact_id=whatsapp_contact_id,
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
        if state == KITCHEN_STATE_READY and order.kitchen_state != KITCHEN_STATE_READY:
            # Sólo en el FLANCO: la cocina reempuja el estado en cada ticket que avanza, y
            # sin esta comparación un pedido ya listo dispararía el aviso en cada empujón.
            # (La constraint de emisión lo atraparía igual; esto ahorra el viaje.)
            await self._notify_customer(tenant_id, order_id, CUSTOMER_STATE_READY)
        return updated

    # --- Items -------------------------------------------------------------
    async def add_item(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        product_variant_id: uuid.UUID,
        quantity: int,
        unit_price: Decimal,
        notes: str | None = None,
    ) -> OrderItem:
        order = await self._require_open_order(tenant_id, order_id)
        if not await self._repo.variant_exists(tenant_id, product_variant_id):
            raise NotFoundError(
                f"Variante de producto no encontrada: {product_variant_id}"
            )
        # Safety net at the sale boundary: never sell a variant that would not deduct
        # stock. Create nothing when the variant has no recipe.
        if not await self._repo.variant_has_recipe(tenant_id, product_variant_id):
            raise ValidationError(
                "El producto no tiene receta; no descontaría inventario."
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
                notes=(notes.strip() or None) if notes else None,
            )
        )
        await self._repo.recompute_totals(tenant_id, order_id)
        # Items are created *pending*: they do NOT auto-route to the kitchen. Staff compose the
        # full order, then trigger routing explicitly ("Enviar a cocina", the kitchen route
        # endpoint) — so a mistaken tap isn't already cooking and an un-sent order cancels clean.
        await self._publish(tenant_id, order.branch_id, "items")
        return item

    async def update_item_quantity(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID, quantity: int
    ) -> OrderItem:
        item = await self._require_item(tenant_id, item_id)
        order = await self._require_open_order(tenant_id, item.order_id)
        if quantity <= 0:
            raise ValidationError("La cantidad debe ser positiva.")
        await self._repo.update_item(tenant_id, item_id, {"quantity": quantity})
        updated = await self._repo.recompute_item(tenant_id, item_id)
        await self._repo.recompute_totals(tenant_id, item.order_id)
        assert updated is not None
        await self._publish(tenant_id, order.branch_id, "items")
        return updated

    async def change_item_variant(
        self,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        product_variant_id: uuid.UUID,
        unit_price: Decimal,
    ) -> OrderItem:
        """Cambia el producto de una línea, conservando su cantidad y sus adiciones.

        No existía: el personal quita y vuelve a poner, que en una comanda de mostrador es
        equivalente. Por la vía pública no lo es — quitar es justo lo que no se le deja hacer
        al cliente—, así que cambiar tiene que ser una sola operación.

        Se repiten aquí las dos redes de seguridad de `add_item` porque una línea que cambia de
        producto es una venta nueva: la variante tiene que existir y tener receta, o estaríamos
        vendiendo algo que no descontaría inventario.
        """
        item = await self._require_item(tenant_id, item_id)
        order = await self._require_open_order(tenant_id, item.order_id)
        if not await self._repo.variant_exists(tenant_id, product_variant_id):
            raise NotFoundError(
                f"Variante de producto no encontrada: {product_variant_id}"
            )
        if not await self._repo.variant_has_recipe(tenant_id, product_variant_id):
            raise ValidationError(
                "El producto no tiene receta; no descontaría inventario."
            )
        await self._repo.update_item(
            tenant_id,
            item_id,
            {"product_variant_id": product_variant_id, "unit_price": unit_price},
        )
        updated = await self._repo.recompute_item(tenant_id, item_id)
        await self._repo.recompute_totals(tenant_id, item.order_id)
        assert updated is not None
        await self._publish(tenant_id, order.branch_id, "items")
        return updated

    async def set_item_notes(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID, notes: str | None
    ) -> OrderItem:
        """Set (or clear) an item's kitchen note.

        Editable for as long as the order is open, including after the item was routed to
        the KDS: the kitchen reads the note from the item at query time, so a correction
        ("sin cebolla") reaches the station instead of being frozen at add time.
        """
        item = await self._require_item(tenant_id, item_id)
        order = await self._require_open_order(tenant_id, item.order_id)
        cleaned = (notes or "").strip() or None
        await self._repo.update_item(tenant_id, item_id, {"notes": cleaned})
        updated = await self._repo.get_item(tenant_id, item_id)
        assert updated is not None
        await self._publish(tenant_id, order.branch_id, "items")
        return updated

    async def remove_item(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> None:
        item = await self._require_item(tenant_id, item_id)
        order = await self._require_open_order(tenant_id, item.order_id)
        await self._repo.delete_item(tenant_id, item_id)
        await self._repo.recompute_totals(tenant_id, item.order_id)
        await self._publish(tenant_id, order.branch_id, "items")

    # --- Addons ------------------------------------------------------------
    async def attach_addon(
        self,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        addon_id: uuid.UUID,
        applied_price: Decimal,
    ) -> OrderItemAddon:
        item = await self._require_item(tenant_id, item_id)
        order = await self._require_open_order(tenant_id, item.order_id)
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
        await self._publish(tenant_id, order.branch_id, "items")
        return addon

    async def detach_addon(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID, item_addon_id: uuid.UUID
    ) -> None:
        item = await self._require_item(tenant_id, item_id)
        order = await self._require_open_order(tenant_id, item.order_id)
        existing = await self._repo.get_item_addon(tenant_id, item_addon_id)
        if existing is None or existing.order_item_id != item_id:
            raise NotFoundError(f"Adición de ítem no encontrada: {item_addon_id}")
        await self._repo.delete_item_addon(tenant_id, item_addon_id)
        await self._repo.recompute_item(tenant_id, item_id)
        await self._repo.recompute_totals(tenant_id, item.order_id)
        await self._publish(tenant_id, order.branch_id, "items")

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
        updated = await self._repo.recompute_totals(tenant_id, order_id)
        await self._publish(tenant_id, order.branch_id, "updated")
        return updated

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
        await self._publish(tenant_id, order.branch_id, "items")

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
        # Y su entrega, por el mismo motivo que la mesa: la comanda se acaba, así que hay que
        # soltar lo que tenía cogido. Una entrega abandonada aquí no puede llegar nunca a cocina
        # y bloquea el cierre de caja de su turno sin salida honesta.
        await self._release_delivery(tenant_id, order)
        assert updated is not None
        await self._publish(tenant_id, order.branch_id, "cancelled")
        await self._notify_customer(tenant_id, order_id, CUSTOMER_STATE_CANCELLED)
        return updated

    async def assign_customer(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, customer_id: uuid.UUID
    ) -> Order:
        """Attach a registered customer to an open order so it can be closed on
        credit (fiado). The order must be open and the customer must exist in the
        tenant. Reassigning while the order is still open is allowed."""
        order = await self._require_open_order(tenant_id, order_id)
        if not await self._repo.customer_exists(tenant_id, customer_id):
            raise NotFoundError(f"Cliente no encontrado: {customer_id}")
        updated = await self._repo.update_order(
            tenant_id, order_id, {"customer_id": customer_id}
        )
        assert updated is not None
        await self._publish(tenant_id, order.branch_id, "updated")
        return updated

    # --- Close / receipts --------------------------------------------------
    async def close_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, *, write_off: bool = False
    ) -> Order:
        """Cierra la comanda. `write_off` absorbe lo impagado como pérdida del negocio.

        Ese modo lo usa SOLO la resolución de una entrega no entregada, y nunca lo expone un
        endpoint: cerrar sin pagar es justo lo que hacía desaparecer las ventas de la caja, y
        la regla ordinaria —pagar completo o fiar a un cliente registrado— sigue en pie para
        todos los demás cierres.

        Se descuenta inventario igual en los dos modos: la comida de un pedido que volvió a la
        tienda se cocinó de todas formas.
        """
        order = await self._require_open_order(tenant_id, order_id)
        # An order may only close once settled: its payments must cover the total,
        # unless a registered customer absorbs the unpaid remainder on credit
        # (fiado). Overpayment (remainder < 0) is change and closes normally.
        paid = await self._repo.payments_total(tenant_id, order_id)
        remainder = order.total - paid
        if remainder > 0 and order.customer_id is None and not write_off:
            # Validate BEFORE mutating: a rejected close deducts no inventory and
            # leaves the order open.
            raise ValidationError(
                f"La comanda no está pagada. Faltan ${remainder}. "
                "Asigna un cliente para fiar."
            )
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
        # La entrega NO se toca al cerrar, y la diferencia con cancelar es todo el asunto:
        # cerrar significa que la comanda está pagada y SIGUE su camino —cocina y luego
        # despacho—, no que se acabó. Su entrega está justo en `pending` esperando que la
        # asignen a un domiciliario; soltarla aquí la borraría del tablero y el pedido, ya
        # cobrado, no lo llevaría nadie. La resuelve quien la entrega.
        assert updated is not None
        # Record the unpaid remainder as a customer credit after a genuine close so
        # `reference_id` points at a closed order. `customer_id` is guaranteed
        # present here (the None case was rejected above).
        #
        # A write-off skips this entirely: the customer never received the food, so charging
        # them for it would turn a failed delivery into a debt they owe us.
        if remainder > 0 and not write_off:
            assert order.customer_id is not None
            await self._repo.create_order_credit(
                tenant_id, order.customer_id, remainder, order_id
            )
        await self._publish(tenant_id, order.branch_id, "closed")
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
