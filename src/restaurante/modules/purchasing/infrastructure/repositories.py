"""Persistence adapter for the Purchasing module over SQLAlchemy async.

Each write commits its own unit of work and filters explicitly by ``tenant_id``
(and ``branch_id`` where applicable). Goods receipt writes an inventory ``in``
movement and bumps stock in one transaction. Unique violations → ``ConflictError``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.cash.infrastructure.models import (
    CashMovementModel,
    CashSessionModel,
)
from restaurante.modules.catalog.infrastructure.models import UnitOfMeasureModel
from restaurante.modules.inventory.infrastructure.models import (
    InventoryMovementModel,
    InventoryStockModel,
)
from restaurante.modules.purchasing.domain.entities import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchasePayment,
    PurchaseRequest,
    PurchaseRequestItem,
    Supplier,
    SupplierIngredient,
)
from restaurante.modules.purchasing.infrastructure.models import (
    PurchaseOrderItemModel,
    PurchaseOrderModel,
    PurchasePaymentModel,
    PurchaseRequestItemModel,
    PurchaseRequestModel,
    SupplierIngredientModel,
    SupplierModel,
)
from restaurante.modules.recipes.infrastructure.models import IngredientModel
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.domain.errors import ConflictError
from restaurante.shared.tenancy.models import BranchModel


def _supplier(m: SupplierModel) -> Supplier:
    return Supplier(
        id=m.id,
        tenant_id=m.tenant_id,
        name=m.name,
        is_active=m.is_active,
        tax_id=m.tax_id,
        phone=m.phone,
        email=m.email,
        address=m.address,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _supplier_ingredient(m: SupplierIngredientModel) -> SupplierIngredient:
    return SupplierIngredient(
        id=m.id,
        tenant_id=m.tenant_id,
        supplier_id=m.supplier_id,
        ingredient_id=m.ingredient_id,
        reference_price=m.reference_price,
        unit_of_measure_id=m.unit_of_measure_id,
        is_active=m.is_active,
    )


def _request(m: PurchaseRequestModel) -> PurchaseRequest:
    return PurchaseRequest(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        requested_by_employee_id=m.requested_by_employee_id,
        status=m.status,
        reason=m.reason,
        approved_by_employee_id=m.approved_by_employee_id,
        resolved_at=m.resolved_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _request_item(m: PurchaseRequestItemModel) -> PurchaseRequestItem:
    return PurchaseRequestItem(
        id=m.id,
        tenant_id=m.tenant_id,
        purchase_request_id=m.purchase_request_id,
        ingredient_id=m.ingredient_id,
        requested_quantity=m.requested_quantity,
        unit_of_measure_id=m.unit_of_measure_id,
    )


def _order(m: PurchaseOrderModel) -> PurchaseOrder:
    return PurchaseOrder(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        purchase_request_id=m.purchase_request_id,
        supplier_id=m.supplier_id,
        status=m.status,
        payment_status=m.payment_status,
        total=m.total,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _order_item(m: PurchaseOrderItemModel) -> PurchaseOrderItem:
    return PurchaseOrderItem(
        id=m.id,
        tenant_id=m.tenant_id,
        purchase_order_id=m.purchase_order_id,
        ingredient_id=m.ingredient_id,
        ordered_quantity=m.ordered_quantity,
        received_quantity=m.received_quantity,
        unit_price=m.unit_price,
        unit_of_measure_id=m.unit_of_measure_id,
    )


def _payment(m: PurchasePaymentModel) -> PurchasePayment:
    return PurchasePayment(
        id=m.id,
        tenant_id=m.tenant_id,
        purchase_order_id=m.purchase_order_id,
        amount=m.amount,
        method=m.method,
        employee_id=m.employee_id,
        paid_at=m.paid_at,
    )


class SqlAlchemyPurchasingRepository:
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

    async def ingredient_exists(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> bool:
        stmt = select(IngredientModel.id).where(
            IngredientModel.id == ingredient_id,
            IngredientModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def unit_exists(self, unit_of_measure_id: uuid.UUID) -> bool:
        stmt = select(UnitOfMeasureModel.id).where(
            UnitOfMeasureModel.id == unit_of_measure_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Suppliers ---------------------------------------------------------
    async def create_supplier(self, supplier: Supplier) -> Supplier:
        model = SupplierModel(
            tenant_id=supplier.tenant_id,
            name=supplier.name,
            tax_id=supplier.tax_id,
            phone=supplier.phone,
            email=supplier.email,
            address=supplier.address,
            is_active=supplier.is_active,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _supplier(model)

    async def _get_supplier_model(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> SupplierModel | None:
        stmt = select(SupplierModel).where(
            SupplierModel.id == supplier_id, SupplierModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_supplier(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> Supplier | None:
        model = await self._get_supplier_model(tenant_id, supplier_id)
        return _supplier(model) if model else None

    async def list_suppliers(
        self, tenant_id: uuid.UUID, *, active: bool | None = None
    ) -> list[Supplier]:
        stmt = select(SupplierModel).where(SupplierModel.tenant_id == tenant_id)
        if active is not None:
            stmt = stmt.where(SupplierModel.is_active.is_(active))
        stmt = stmt.order_by(SupplierModel.name)
        return [_supplier(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_supplier(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID, fields: dict[str, Any]
    ) -> Supplier | None:
        model = await self._get_supplier_model(tenant_id, supplier_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _supplier(model)

    # --- Supplier ingredients ----------------------------------------------
    async def create_supplier_ingredient(
        self, mapping: SupplierIngredient
    ) -> SupplierIngredient:
        model = SupplierIngredientModel(
            tenant_id=mapping.tenant_id,
            supplier_id=mapping.supplier_id,
            ingredient_id=mapping.ingredient_id,
            reference_price=mapping.reference_price,
            unit_of_measure_id=mapping.unit_of_measure_id,
            is_active=mapping.is_active,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(
                "El insumo ya está registrado para ese proveedor."
            ) from exc
        await self._session.refresh(model)
        return _supplier_ingredient(model)

    async def supplier_ingredient_exists(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> bool:
        stmt = select(SupplierIngredientModel.id).where(
            SupplierIngredientModel.tenant_id == tenant_id,
            SupplierIngredientModel.supplier_id == supplier_id,
            SupplierIngredientModel.ingredient_id == ingredient_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def list_supplier_ingredients(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> list[SupplierIngredient]:
        stmt = select(SupplierIngredientModel).where(
            SupplierIngredientModel.tenant_id == tenant_id,
            SupplierIngredientModel.supplier_id == supplier_id,
        )
        return [
            _supplier_ingredient(m)
            for m in (await self._session.execute(stmt)).scalars()
        ]

    async def delete_supplier_ingredient(
        self, tenant_id: uuid.UUID, supplier_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            sql_delete(SupplierIngredientModel).where(
                SupplierIngredientModel.tenant_id == tenant_id,
                SupplierIngredientModel.supplier_id == supplier_id,
                SupplierIngredientModel.ingredient_id == ingredient_id,
            )
        )
        await self._session.commit()

    # --- Purchase requests -------------------------------------------------
    async def create_request(
        self, request: PurchaseRequest, items: list[PurchaseRequestItem]
    ) -> PurchaseRequest:
        model = PurchaseRequestModel(
            tenant_id=request.tenant_id,
            branch_id=request.branch_id,
            requested_by_employee_id=request.requested_by_employee_id,
            status=request.status,
            reason=request.reason,
        )
        self._session.add(model)
        await self._session.flush()
        for item in items:
            self._session.add(
                PurchaseRequestItemModel(
                    tenant_id=request.tenant_id,
                    purchase_request_id=model.id,
                    ingredient_id=item.ingredient_id,
                    requested_quantity=item.requested_quantity,
                    unit_of_measure_id=item.unit_of_measure_id,
                )
            )
        await self._session.commit()
        await self._session.refresh(model)
        return _request(model)

    async def _get_request_model(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID
    ) -> PurchaseRequestModel | None:
        stmt = select(PurchaseRequestModel).where(
            PurchaseRequestModel.id == request_id,
            PurchaseRequestModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_request(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID
    ) -> PurchaseRequest | None:
        model = await self._get_request_model(tenant_id, request_id)
        return _request(model) if model else None

    async def list_request_items(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID
    ) -> list[PurchaseRequestItem]:
        stmt = select(PurchaseRequestItemModel).where(
            PurchaseRequestItemModel.tenant_id == tenant_id,
            PurchaseRequestItemModel.purchase_request_id == request_id,
        )
        return [_request_item(m) for m in (await self._session.execute(stmt)).scalars()]

    async def list_requests(
        self, tenant_id: uuid.UUID, *, status: str | None = None
    ) -> list[PurchaseRequest]:
        stmt = select(PurchaseRequestModel).where(
            PurchaseRequestModel.tenant_id == tenant_id
        )
        if status is not None:
            stmt = stmt.where(PurchaseRequestModel.status == status)
        stmt = stmt.order_by(PurchaseRequestModel.created_at.desc())
        return [_request(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_request(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID, fields: dict[str, Any]
    ) -> PurchaseRequest | None:
        model = await self._get_request_model(tenant_id, request_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _request(model)

    # --- Purchase orders ---------------------------------------------------
    async def create_order(
        self, order: PurchaseOrder, items: list[PurchaseOrderItem]
    ) -> PurchaseOrder:
        model = PurchaseOrderModel(
            tenant_id=order.tenant_id,
            branch_id=order.branch_id,
            purchase_request_id=order.purchase_request_id,
            supplier_id=order.supplier_id,
            status=order.status,
            payment_status=order.payment_status,
            total=order.total,
        )
        self._session.add(model)
        await self._session.flush()
        for item in items:
            self._session.add(
                PurchaseOrderItemModel(
                    tenant_id=order.tenant_id,
                    purchase_order_id=model.id,
                    ingredient_id=item.ingredient_id,
                    ordered_quantity=item.ordered_quantity,
                    received_quantity=item.received_quantity,
                    unit_price=item.unit_price,
                    unit_of_measure_id=item.unit_of_measure_id,
                )
            )
        await self._session.commit()
        await self._session.refresh(model)
        return _order(model)

    async def _get_order_model(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> PurchaseOrderModel | None:
        stmt = select(PurchaseOrderModel).where(
            PurchaseOrderModel.id == order_id,
            PurchaseOrderModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> PurchaseOrder | None:
        model = await self._get_order_model(tenant_id, order_id)
        return _order(model) if model else None

    async def list_order_items(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[PurchaseOrderItem]:
        stmt = select(PurchaseOrderItemModel).where(
            PurchaseOrderItemModel.tenant_id == tenant_id,
            PurchaseOrderItemModel.purchase_order_id == order_id,
        )
        return [_order_item(m) for m in (await self._session.execute(stmt)).scalars()]

    async def get_order_item(
        self, tenant_id: uuid.UUID, order_item_id: uuid.UUID
    ) -> PurchaseOrderItem | None:
        stmt = select(PurchaseOrderItemModel).where(
            PurchaseOrderItemModel.id == order_item_id,
            PurchaseOrderItemModel.tenant_id == tenant_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _order_item(model) if model else None

    async def list_orders(
        self, tenant_id: uuid.UUID, *, status: str | None = None
    ) -> list[PurchaseOrder]:
        stmt = select(PurchaseOrderModel).where(
            PurchaseOrderModel.tenant_id == tenant_id
        )
        if status is not None:
            stmt = stmt.where(PurchaseOrderModel.status == status)
        stmt = stmt.order_by(PurchaseOrderModel.created_at.desc())
        return [_order(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, fields: dict[str, Any]
    ) -> PurchaseOrder | None:
        model = await self._get_order_model(tenant_id, order_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _order(model)

    # --- Goods receipt -----------------------------------------------------
    async def receive_item(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        order_id: uuid.UUID,
        order_item: PurchaseOrderItem,
        quantity: Decimal,
        employee_id: uuid.UUID,
    ) -> None:
        item_model = (
            await self._session.execute(
                select(PurchaseOrderItemModel).where(
                    PurchaseOrderItemModel.id == order_item.id,
                    PurchaseOrderItemModel.tenant_id == tenant_id,
                )
            )
        ).scalar_one()
        item_model.received_quantity = item_model.received_quantity + quantity

        stock = (
            await self._session.execute(
                select(InventoryStockModel).where(
                    InventoryStockModel.tenant_id == tenant_id,
                    InventoryStockModel.branch_id == branch_id,
                    InventoryStockModel.ingredient_id == order_item.ingredient_id,
                )
            )
        ).scalar_one_or_none()
        if stock is None:
            stock = InventoryStockModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                ingredient_id=order_item.ingredient_id,
                current_quantity=quantity,
                min_stock=Decimal(0),
            )
            self._session.add(stock)
        else:
            stock.current_quantity = stock.current_quantity + quantity

        self._session.add(
            InventoryMovementModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                ingredient_id=order_item.ingredient_id,
                type="in",
                reason="purchase",
                quantity=quantity,
                employee_id=employee_id,
                reference_id=order_id,
            )
        )
        await self._session.commit()

    # --- Payments ----------------------------------------------------------
    async def get_open_cash_session_id(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> uuid.UUID | None:
        stmt = select(CashSessionModel.id).where(
            CashSessionModel.tenant_id == tenant_id,
            CashSessionModel.branch_id == branch_id,
            CashSessionModel.status == "open",
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def create_payment(
        self,
        payment: PurchasePayment,
        *,
        cash_session_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
    ) -> PurchasePayment:
        """Persist the payment and, for cash, a matching drawer `out` movement atomically."""
        model = PurchasePaymentModel(
            tenant_id=payment.tenant_id,
            purchase_order_id=payment.purchase_order_id,
            amount=payment.amount,
            method=payment.method,
            employee_id=payment.employee_id,
        )
        self._session.add(model)
        if cash_session_id is not None and branch_id is not None:
            self._session.add(
                CashMovementModel(
                    tenant_id=payment.tenant_id,
                    branch_id=branch_id,
                    cash_session_id=cash_session_id,
                    type="out",
                    concept="purchase_payment",
                    amount=payment.amount,
                    method=payment.method,
                    reference_id=payment.purchase_order_id,
                )
            )
        await self._session.commit()
        await self._session.refresh(model)
        return _payment(model)

    async def list_payments(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[PurchasePayment]:
        stmt = (
            select(PurchasePaymentModel)
            .where(
                PurchasePaymentModel.tenant_id == tenant_id,
                PurchasePaymentModel.purchase_order_id == order_id,
            )
            .order_by(PurchasePaymentModel.paid_at)
        )
        return [_payment(m) for m in (await self._session.execute(stmt)).scalars()]

    async def payments_total(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Decimal:
        stmt = select(
            func.coalesce(func.sum(PurchasePaymentModel.amount), 0)
        ).where(
            PurchasePaymentModel.tenant_id == tenant_id,
            PurchasePaymentModel.purchase_order_id == order_id,
        )
        return Decimal(str((await self._session.execute(stmt)).scalar_one()))
