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
    OrderPaymentClaim,
    OrderRefund,
    ReceiptPrint,
)


class KitchenRouting(Protocol):
    """Outbound port: route an order to the kitchen (create KDS tickets for routable items).

    Kept here so the orders application depends on an interface, not the kitchen module — the
    concrete adapter is wired at the composition root, preserving a one-way module dependency.
    """

    async def route_order(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> None: ...


class DeliveryQuoteGate(Protocol):
    """Outbound port: ¿está el domicilio de este pedido en condiciones de cobrarse?

    Existe porque un domicilio sin cotizar tiene un `total` que TODAVÍA NO incluye el domicilio.
    Verificar el pago en ese instante cobra de menos, manda la comida a cocina, y la diferencia
    aparece en la puerta — con el pedido ya entregado y sin nada que hacer.

    Puerto y no un import de `delivery` por lo de siempre: cobrar tiene que poder ocurrir sin el
    módulo de domicilios montado. Sin adaptador enchufado, la puerta está abierta y el
    comportamiento es exactamente el de antes.
    """

    async def quote_blocker(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> str | None:
        """Motivo por el que este pedido no puede cobrarse aún, o None si puede.

        Devuelve una frase para una persona, no un código: quien la lee está delante del
        cliente y necesita saber qué decirle.
        """
        ...


class PaymentClaimNotifier(Protocol):
    """Outbound port: decirle al cliente en qué quedó el comprobante que mandó.

    Puerto y no un import de messaging por lo de siempre: el cobro tiene que poder ocurrir con
    WhatsApp completamente ausente. Sin adaptador enchufado, resolver un comprobante no avisa a
    nadie y todo lo demás funciona igual.
    """

    async def notify_payment_claim(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        status: str,
        reason: str | None,
    ) -> None: ...


class DeliveryDispatch(Protocol):
    """Outbound port: ensure a `delivery` order has its delivery record (Dispatch entry).

    Kept here so the orders application depends on an interface, not the delivery module — the
    concrete adapter is wired at the composition root. The implementation MUST be idempotent
    (do nothing if the order already has a delivery record).
    """

    async def ensure_delivery_for_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> None: ...

    async def release_delivery_for_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> None:
        """Suelta la entrega de un pedido que deja de existir. NUNCA levanta.

        Es la misma obligación que liberar la mesa: la comanda se acaba, así que todo lo que
        tenía cogido hay que soltarlo. Una entrega abandonada no puede llegar nunca a cocina
        —su comanda ya no está— y bloquea el cierre de caja de su turno sin salida honesta.

        SÓLO suelta la entrega que nunca salió del local. Una que ya va con un domiciliario no
        se toca: alguien salió con esa comida y el desenlace es suyo. La implementación es
        idempotente — un pedido sin entrega, o con una ya resuelta, no cambia nada.
        """
        ...


class OrdersRepository(Protocol):
    # --- Reference existence checks ----------------------------------------
    async def branch_exists(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool: ...

    async def employee_exists(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool: ...

    async def customer_exists(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID
    ) -> bool: ...

    async def variant_exists(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> bool: ...

    async def variant_has_recipe(
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

    async def set_edit_token(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        token: str,
        expires_at: datetime,
    ) -> None:
        """Acuña el enlace con el que el cliente edita ESTE pedido."""
        ...

    async def get_order_by_edit_token(self, token: str) -> Order | None:
        """El pedido detrás de un token, sin filtrar por tenant.

        No lleva `tenant_id` a propósito: el token es global y quien lo resuelve todavía no
        sabe de quién es. Comprobar que el pedido pertenece al tenant de la petición es
        trabajo de quien llama — igual que ya hace `resolve_store_token`.
        """
        ...

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
        open_session_only: bool = False,
        whatsapp_contact_id: uuid.UUID | None = None,
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

    async def payments_total(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Decimal: ...

    # --- Payment claims (una declaración del cliente, NUNCA un pago) -------
    async def create_payment_claim(
        self, claim: OrderPaymentClaim
    ) -> OrderPaymentClaim: ...

    async def list_payment_claims(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[OrderPaymentClaim]: ...

    async def count_pending_payment_claims(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> int: ...

    async def get_payment_claim(
        self, tenant_id: uuid.UUID, claim_id: uuid.UUID
    ) -> OrderPaymentClaim | None: ...

    async def resolve_payment_claims(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        *,
        status: str,
        employee_id: uuid.UUID | None,
        reason: str | None = None,
        claim_id: uuid.UUID | None = None,
    ) -> list[OrderPaymentClaim]:
        """Resuelve las pendientes del pedido (o una concreta) y devuelve las que cambiaron."""
        ...

    # --- Refunds -----------------------------------------------------------
    async def create_refund(self, refund: OrderRefund) -> OrderRefund: ...

    async def get_refund(
        self, tenant_id: uuid.UUID, refund_id: uuid.UUID
    ) -> OrderRefund | None: ...

    async def refund_for_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderRefund | None: ...

    async def list_refunds(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[OrderRefund]: ...

    async def resolve_refund(
        self,
        tenant_id: uuid.UUID,
        refund_id: uuid.UUID,
        *,
        status: str,
        employee_id: uuid.UUID,
        reason: str | None,
    ) -> OrderRefund | None: ...

    async def register_refund_movement(self, refund: OrderRefund) -> None:
        """Movimiento de caja `out` por el monto devuelto, con el método ORIGINAL.

        Nunca efectivo salvo que el pago original lo fuera: el arqueo solo cuenta `cash`, y
        registrar ahí una devolución por transferencia haría que esperara menos plata en el
        cajón de la que hay.
        """
        ...

    async def create_order_credit(
        self,
        tenant_id: uuid.UUID,
        customer_id: uuid.UUID,
        amount: Decimal,
        order_id: uuid.UUID,
    ) -> None: ...

    # --- Inventory deduction (orders ↔ recipes ↔ inventory) ----------------
    async def consume_inventory_for_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> None: ...
