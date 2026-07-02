"""Application service for the Purchasing module (procure-to-pay).

Owns suppliers and their ingredient catalog, purchase requests with approval,
purchase orders, goods receipt (which feeds inventory), and supplier payments.
Totals and statuses are derived server-side; cross-entity rules are enforced here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from restaurante.modules.purchasing.domain.entities import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchasePayment,
    PurchaseRequest,
    PurchaseRequestItem,
    Supplier,
    SupplierIngredient,
)
from restaurante.modules.purchasing.domain.ports import PurchasingRepository
from restaurante.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

REQ_PENDING = "pending"
REQ_APPROVED = "approved"
REQ_REJECTED = "rejected"

ORDER_CREATED = "created"
ORDER_PARTIALLY_RECEIVED = "partially_received"
ORDER_RECEIVED = "received"

PAY_PENDING = "pending"
PAY_PARTIAL = "partial"
PAY_PAID = "paid"


class PurchasingService:
    def __init__(self, repo: PurchasingRepository) -> None:
        self._repo = repo

    # --- guards ------------------------------------------------------------
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

    async def _require_ingredient(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> None:
        if not await self._repo.ingredient_exists(tenant_id, ingredient_id):
            raise NotFoundError(f"Insumo no encontrado: {ingredient_id}")

    async def _require_unit(self, unit_of_measure_id: uuid.UUID) -> None:
        if not await self._repo.unit_exists(unit_of_measure_id):
            raise NotFoundError(
                f"Unidad de medida no encontrada: {unit_of_measure_id}"
            )

    async def _require_supplier(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> Supplier:
        supplier = await self._repo.get_supplier(tenant_id, supplier_id)
        if supplier is None:
            raise NotFoundError(f"Proveedor no encontrado: {supplier_id}")
        return supplier

    async def _require_request(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID
    ) -> PurchaseRequest:
        request = await self._repo.get_request(tenant_id, request_id)
        if request is None:
            raise NotFoundError(f"Solicitud de compra no encontrada: {request_id}")
        return request

    async def _require_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> PurchaseOrder:
        order = await self._repo.get_order(tenant_id, order_id)
        if order is None:
            raise NotFoundError(f"Orden de compra no encontrada: {order_id}")
        return order

    # --- Suppliers ---------------------------------------------------------
    async def create_supplier(
        self,
        tenant_id: uuid.UUID,
        name: str,
        tax_id: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        address: str | None = None,
    ) -> Supplier:
        return await self._repo.create_supplier(
            Supplier(
                tenant_id=tenant_id,
                name=name,
                tax_id=tax_id,
                phone=phone,
                email=email,
                address=address,
            )
        )

    async def list_suppliers(
        self, tenant_id: uuid.UUID, *, active: bool | None = None
    ) -> list[Supplier]:
        return await self._repo.list_suppliers(tenant_id, active=active)

    async def get_supplier(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> Supplier:
        return await self._require_supplier(tenant_id, supplier_id)

    async def update_supplier(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID, fields: dict[str, Any]
    ) -> Supplier:
        updated = await self._repo.update_supplier(tenant_id, supplier_id, fields)
        if updated is None:
            raise NotFoundError(f"Proveedor no encontrado: {supplier_id}")
        return updated

    async def deactivate_supplier(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> Supplier:
        await self._require_supplier(tenant_id, supplier_id)
        return await self.update_supplier(tenant_id, supplier_id, {"is_active": False})

    # --- Supplier ingredients ----------------------------------------------
    async def attach_supplier_ingredient(
        self,
        tenant_id: uuid.UUID,
        supplier_id: uuid.UUID,
        ingredient_id: uuid.UUID,
        reference_price: Decimal,
        unit_of_measure_id: uuid.UUID,
    ) -> SupplierIngredient:
        await self._require_supplier(tenant_id, supplier_id)
        await self._require_ingredient(tenant_id, ingredient_id)
        await self._require_unit(unit_of_measure_id)
        if reference_price < 0:
            raise ValidationError("El precio de referencia no puede ser negativo.")
        if await self._repo.supplier_ingredient_exists(
            tenant_id, supplier_id, ingredient_id
        ):
            raise ConflictError("El insumo ya está registrado para ese proveedor.")
        return await self._repo.create_supplier_ingredient(
            SupplierIngredient(
                tenant_id=tenant_id,
                supplier_id=supplier_id,
                ingredient_id=ingredient_id,
                reference_price=reference_price,
                unit_of_measure_id=unit_of_measure_id,
            )
        )

    async def list_supplier_ingredients(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> list[SupplierIngredient]:
        await self._require_supplier(tenant_id, supplier_id)
        return await self._repo.list_supplier_ingredients(tenant_id, supplier_id)

    async def detach_supplier_ingredient(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> None:
        await self._repo.delete_supplier_ingredient(
            tenant_id, supplier_id, ingredient_id
        )

    # --- Purchase requests -------------------------------------------------
    async def create_request(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        requested_by_employee_id: uuid.UUID,
        items: list[dict[str, Any]],
        reason: str | None = None,
    ) -> PurchaseRequest:
        await self._require_branch(tenant_id, branch_id)
        await self._require_employee(tenant_id, requested_by_employee_id)
        if not items:
            raise ValidationError("La solicitud debe tener al menos un ítem.")
        entities: list[PurchaseRequestItem] = []
        for item in items:
            await self._require_ingredient(tenant_id, item["ingredient_id"])
            await self._require_unit(item["unit_of_measure_id"])
            if item["requested_quantity"] <= 0:
                raise ValidationError("La cantidad solicitada debe ser positiva.")
            entities.append(
                PurchaseRequestItem(
                    tenant_id=tenant_id,
                    purchase_request_id=uuid.uuid4(),  # replaced on persist
                    ingredient_id=item["ingredient_id"],
                    requested_quantity=item["requested_quantity"],
                    unit_of_measure_id=item["unit_of_measure_id"],
                )
            )
        return await self._repo.create_request(
            PurchaseRequest(
                tenant_id=tenant_id,
                branch_id=branch_id,
                requested_by_employee_id=requested_by_employee_id,
                reason=reason,
            ),
            entities,
        )

    async def get_request(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID
    ) -> PurchaseRequest:
        return await self._require_request(tenant_id, request_id)

    async def list_request_items(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID
    ) -> list[PurchaseRequestItem]:
        await self._require_request(tenant_id, request_id)
        return await self._repo.list_request_items(tenant_id, request_id)

    async def list_requests(
        self, tenant_id: uuid.UUID, *, status: str | None = None
    ) -> list[PurchaseRequest]:
        return await self._repo.list_requests(tenant_id, status=status)

    async def _resolve_request(
        self,
        tenant_id: uuid.UUID,
        request_id: uuid.UUID,
        new_status: str,
        approver_id: uuid.UUID,
    ) -> PurchaseRequest:
        request = await self._require_request(tenant_id, request_id)
        await self._require_employee(tenant_id, approver_id)
        if request.status != REQ_PENDING:
            raise ConflictError(
                f"La solicitud no está pendiente (estado: {request.status})."
            )
        updated = await self._repo.update_request(
            tenant_id,
            request_id,
            {
                "status": new_status,
                "approved_by_employee_id": approver_id,
                "resolved_at": datetime.now(UTC),
            },
        )
        assert updated is not None
        return updated

    async def approve_request(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID, approver_id: uuid.UUID
    ) -> PurchaseRequest:
        return await self._resolve_request(
            tenant_id, request_id, REQ_APPROVED, approver_id
        )

    async def reject_request(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID, approver_id: uuid.UUID
    ) -> PurchaseRequest:
        return await self._resolve_request(
            tenant_id, request_id, REQ_REJECTED, approver_id
        )

    # --- Purchase orders ---------------------------------------------------
    async def create_order(
        self,
        tenant_id: uuid.UUID,
        purchase_request_id: uuid.UUID,
        supplier_id: uuid.UUID,
        items: list[dict[str, Any]],
    ) -> PurchaseOrder:
        request = await self._require_request(tenant_id, purchase_request_id)
        if request.status != REQ_APPROVED:
            raise ConflictError("La solicitud de compra no está aprobada.")
        await self._require_supplier(tenant_id, supplier_id)
        if not items:
            raise ValidationError("La orden debe tener al menos un ítem.")
        entities: list[PurchaseOrderItem] = []
        total = Decimal(0)
        for item in items:
            await self._require_ingredient(tenant_id, item["ingredient_id"])
            await self._require_unit(item["unit_of_measure_id"])
            if item["ordered_quantity"] <= 0:
                raise ValidationError("La cantidad pedida debe ser positiva.")
            if item["unit_price"] < 0:
                raise ValidationError("El precio unitario no puede ser negativo.")
            total += item["ordered_quantity"] * item["unit_price"]
            entities.append(
                PurchaseOrderItem(
                    tenant_id=tenant_id,
                    purchase_order_id=uuid.uuid4(),  # replaced on persist
                    ingredient_id=item["ingredient_id"],
                    ordered_quantity=item["ordered_quantity"],
                    unit_price=item["unit_price"],
                    unit_of_measure_id=item["unit_of_measure_id"],
                )
            )
        return await self._repo.create_order(
            PurchaseOrder(
                tenant_id=tenant_id,
                branch_id=request.branch_id,
                purchase_request_id=purchase_request_id,
                supplier_id=supplier_id,
                total=total,
            ),
            entities,
        )

    async def get_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> PurchaseOrder:
        return await self._require_order(tenant_id, order_id)

    async def list_order_items(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[PurchaseOrderItem]:
        await self._require_order(tenant_id, order_id)
        return await self._repo.list_order_items(tenant_id, order_id)

    async def list_orders(
        self, tenant_id: uuid.UUID, *, status: str | None = None
    ) -> list[PurchaseOrder]:
        return await self._repo.list_orders(tenant_id, status=status)

    # --- Goods receipt -----------------------------------------------------
    async def receive_items(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        receipts: list[dict[str, Any]],
        received_by_employee_id: uuid.UUID,
    ) -> PurchaseOrder:
        order = await self._require_order(tenant_id, order_id)
        await self._require_employee(tenant_id, received_by_employee_id)
        if not receipts:
            raise ValidationError("Debe recibir al menos un ítem.")
        for receipt in receipts:
            quantity = receipt["quantity"]
            if quantity <= 0:
                raise ValidationError("La cantidad recibida debe ser positiva.")
            item = await self._repo.get_order_item(tenant_id, receipt["order_item_id"])
            if item is None or item.purchase_order_id != order_id:
                raise NotFoundError(
                    f"Ítem de orden no encontrado: {receipt['order_item_id']}"
                )
            await self._repo.receive_item(
                tenant_id,
                order.branch_id,
                order_id,
                item,
                quantity,
                received_by_employee_id,
            )
        # Recompute order status from the (now updated) items.
        items = await self._repo.list_order_items(tenant_id, order_id)
        fully = all(i.received_quantity >= i.ordered_quantity for i in items)
        any_received = any(i.received_quantity > 0 for i in items)
        new_status = (
            ORDER_RECEIVED
            if fully
            else (ORDER_PARTIALLY_RECEIVED if any_received else ORDER_CREATED)
        )
        updated = await self._repo.update_order(
            tenant_id, order_id, {"status": new_status}
        )
        assert updated is not None
        return updated

    # --- Payments ----------------------------------------------------------
    async def register_payment(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        amount: Decimal,
        method: str,
        employee_id: uuid.UUID,
    ) -> PurchasePayment:
        order = await self._require_order(tenant_id, order_id)
        await self._require_employee(tenant_id, employee_id)
        if amount <= 0:
            raise ValidationError("El monto del pago debe ser positivo.")
        # A cash payment leaves the drawer: require the order branch's open cash session and post
        # a matching `out` movement atomically. Non-cash methods do not touch the cash session.
        cash_session_id: uuid.UUID | None = None
        if method == "cash":
            cash_session_id = await self._repo.get_open_cash_session_id(
                tenant_id, order.branch_id
            )
            if cash_session_id is None:
                raise ConflictError(
                    "No hay sesión de caja abierta en la sucursal para registrar el "
                    "pago en efectivo."
                )
        payment = await self._repo.create_payment(
            PurchasePayment(
                tenant_id=tenant_id,
                purchase_order_id=order_id,
                amount=amount,
                method=method,
                employee_id=employee_id,
            ),
            cash_session_id=cash_session_id,
            branch_id=order.branch_id if cash_session_id is not None else None,
        )
        paid = await self._repo.payments_total(tenant_id, order_id)
        if paid >= order.total and order.total > 0:
            payment_status = PAY_PAID
        elif paid > 0:
            payment_status = PAY_PARTIAL
        else:
            payment_status = PAY_PENDING
        await self._repo.update_order(
            tenant_id, order_id, {"payment_status": payment_status}
        )
        return payment

    async def list_payments(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[PurchasePayment]:
        await self._require_order(tenant_id, order_id)
        return await self._repo.list_payments(tenant_id, order_id)
