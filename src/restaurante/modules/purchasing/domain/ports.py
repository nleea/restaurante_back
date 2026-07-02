"""Ports (interfaces) of the Purchasing module."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Protocol

from restaurante.modules.purchasing.domain.entities import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchasePayment,
    PurchaseRequest,
    PurchaseRequestItem,
    Supplier,
    SupplierIngredient,
)


class PurchasingRepository(Protocol):
    # --- Reference existence checks ----------------------------------------
    async def branch_exists(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool: ...

    async def employee_exists(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool: ...

    async def ingredient_exists(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> bool: ...

    async def unit_exists(self, unit_of_measure_id: uuid.UUID) -> bool: ...

    # --- Suppliers ---------------------------------------------------------
    async def create_supplier(self, supplier: Supplier) -> Supplier: ...

    async def get_supplier(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> Supplier | None: ...

    async def list_suppliers(
        self, tenant_id: uuid.UUID, *, active: bool | None = None
    ) -> list[Supplier]: ...

    async def update_supplier(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID, fields: dict[str, Any]
    ) -> Supplier | None: ...

    # --- Supplier ingredients ----------------------------------------------
    async def create_supplier_ingredient(
        self, mapping: SupplierIngredient
    ) -> SupplierIngredient: ...

    async def supplier_ingredient_exists(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> bool: ...

    async def list_supplier_ingredients(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> list[SupplierIngredient]: ...

    async def delete_supplier_ingredient(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> None: ...

    # --- Purchase requests -------------------------------------------------
    async def create_request(
        self, request: PurchaseRequest, items: list[PurchaseRequestItem]
    ) -> PurchaseRequest: ...

    async def get_request(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID
    ) -> PurchaseRequest | None: ...

    async def list_request_items(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID
    ) -> list[PurchaseRequestItem]: ...

    async def list_requests(
        self, tenant_id: uuid.UUID, *, status: str | None = None
    ) -> list[PurchaseRequest]: ...

    async def update_request(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID, fields: dict[str, Any]
    ) -> PurchaseRequest | None: ...

    # --- Purchase orders ---------------------------------------------------
    async def create_order(
        self, order: PurchaseOrder, items: list[PurchaseOrderItem]
    ) -> PurchaseOrder: ...

    async def get_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> PurchaseOrder | None: ...

    async def list_order_items(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[PurchaseOrderItem]: ...

    async def get_order_item(
        self, tenant_id: uuid.UUID, order_item_id: uuid.UUID
    ) -> PurchaseOrderItem | None: ...

    async def list_orders(
        self, tenant_id: uuid.UUID, *, status: str | None = None
    ) -> list[PurchaseOrder]: ...

    async def update_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, fields: dict[str, Any]
    ) -> PurchaseOrder | None: ...

    # --- Goods receipt -----------------------------------------------------
    async def receive_item(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        order_id: uuid.UUID,
        order_item: PurchaseOrderItem,
        quantity: Decimal,
        employee_id: uuid.UUID,
    ) -> None: ...

    # --- Payments ----------------------------------------------------------
    async def get_open_cash_session_id(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> uuid.UUID | None: ...

    async def create_payment(
        self,
        payment: PurchasePayment,
        *,
        cash_session_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
    ) -> PurchasePayment: ...

    async def list_payments(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[PurchasePayment]: ...

    async def payments_total(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Decimal: ...
