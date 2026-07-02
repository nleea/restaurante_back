"""Payment use case for the Orders module — the orders ↔ cash integration.

Charging an order registers an `order_payments` row tied to the branch's open
cash session and, atomically, a `cash_movements` row (type `in`, concept `sale`)
so the arqueo reflects the sale. Payments do not change the order status.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from restaurante.modules.orders.domain.entities import Order, OrderPayment
from restaurante.modules.orders.domain.ports import OrdersRepository
from restaurante.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

ORDER_OPEN = "open"


class PaymentService:
    def __init__(self, repo: OrdersRepository) -> None:
        self._repo = repo

    async def _require_open_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Order:
        order = await self._repo.get_order(tenant_id, order_id)
        if order is None:
            raise NotFoundError(f"Orden no encontrada: {order_id}")
        if order.status != ORDER_OPEN:
            raise ConflictError(
                f"La orden no está abierta (estado: {order.status})."
            )
        return order

    async def register_payment(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        amount: Decimal,
        method: str,
        employee_id: uuid.UUID,
        diner_reference: str | None = None,
    ) -> OrderPayment:
        order = await self._require_open_order(tenant_id, order_id)
        if not await self._repo.employee_exists(tenant_id, employee_id):
            raise NotFoundError(f"Empleado no encontrado: {employee_id}")
        if amount <= 0:
            raise ValidationError("El monto del pago debe ser positivo.")
        session = await self._repo.get_open_cash_session(tenant_id, order.branch_id)
        if session is None:
            raise ConflictError(
                "No hay sesión de caja abierta en la sucursal para registrar el pago."
            )
        assert session.id is not None
        return await self._repo.register_payment(
            OrderPayment(
                tenant_id=tenant_id,
                branch_id=order.branch_id,
                order_id=order_id,
                cash_session_id=session.id,
                amount=amount,
                method=method,
                employee_id=employee_id,
                diner_reference=diner_reference,
            )
        )

    async def list_payments(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[OrderPayment]:
        order = await self._repo.get_order(tenant_id, order_id)
        if order is None:
            raise NotFoundError(f"Orden no encontrada: {order_id}")
        return await self._repo.list_payments(tenant_id, order_id)
