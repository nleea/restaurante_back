"""Application service for the Customers module.

Owns customers (created together with their backing person), preferences, and
store credit (fiado) with settlement payments. Credit `payment_status` is derived
from the sum of payments. Stats are not maintained here (future orders integration).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from restaurante.modules.customers.domain.entities import (
    Customer,
    CustomerCredit,
    CustomerCreditPayment,
    CustomerPreference,
)
from restaurante.modules.customers.domain.ports import CustomersRepository
from restaurante.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

CREDIT_PENDING = "pending"
CREDIT_PARTIAL = "partial"
CREDIT_PAID = "paid"


class CustomerService:
    def __init__(self, repo: CustomersRepository) -> None:
        self._repo = repo

    # --- guards ------------------------------------------------------------
    async def _require_customer(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID
    ) -> Customer:
        customer = await self._repo.get_customer(tenant_id, customer_id)
        if customer is None:
            raise NotFoundError(f"Cliente no encontrado: {customer_id}")
        return customer

    async def _require_credit(
        self, tenant_id: uuid.UUID, credit_id: uuid.UUID
    ) -> CustomerCredit:
        credit = await self._repo.get_credit(tenant_id, credit_id)
        if credit is None:
            raise NotFoundError(f"Crédito no encontrado: {credit_id}")
        return credit

    async def _require_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> None:
        if not await self._repo.employee_exists(tenant_id, employee_id):
            raise NotFoundError(f"Empleado no encontrado: {employee_id}")

    # --- Customers ---------------------------------------------------------
    async def create_customer(
        self,
        tenant_id: uuid.UUID,
        first_name: str,
        last_name: str,
        *,
        document_number: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> Customer:
        if user_id is not None and not await self._repo.user_exists(tenant_id, user_id):
            raise NotFoundError(f"Usuario no encontrado: {user_id}")
        person_fields: dict[str, Any] = {
            "first_name": first_name,
            "last_name": last_name,
            "document_number": document_number,
            "phone": phone,
            "email": email,
        }
        return await self._repo.create_customer(
            person_fields,
            Customer(tenant_id=tenant_id, person_id=uuid.uuid4(), user_id=user_id),
        )

    async def list_customers(
        self, tenant_id: uuid.UUID, *, active: bool | None = None
    ) -> list[Customer]:
        return await self._repo.list_customers(tenant_id, active=active)

    async def get_customer(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID
    ) -> Customer:
        return await self._require_customer(tenant_id, customer_id)

    async def update_customer(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID, fields: dict[str, Any]
    ) -> Customer:
        if fields.get("user_id") is not None and not await self._repo.user_exists(
            tenant_id, fields["user_id"]
        ):
            raise NotFoundError(f"Usuario no encontrado: {fields['user_id']}")
        updated = await self._repo.update_customer(tenant_id, customer_id, fields)
        if updated is None:
            raise NotFoundError(f"Cliente no encontrado: {customer_id}")
        return updated

    async def deactivate_customer(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID
    ) -> Customer:
        await self._require_customer(tenant_id, customer_id)
        updated = await self._repo.update_customer(
            tenant_id, customer_id, {"is_active": False}
        )
        assert updated is not None
        return updated

    # --- Preferences -------------------------------------------------------
    async def set_preference(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID, key: str, value: str
    ) -> CustomerPreference:
        await self._require_customer(tenant_id, customer_id)
        return await self._repo.set_preference(
            CustomerPreference(
                tenant_id=tenant_id, customer_id=customer_id, key=key, value=value
            )
        )

    async def list_preferences(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID
    ) -> list[CustomerPreference]:
        await self._require_customer(tenant_id, customer_id)
        return await self._repo.list_preferences(tenant_id, customer_id)

    async def delete_preference(
        self, tenant_id: uuid.UUID, preference_id: uuid.UUID
    ) -> None:
        await self._repo.delete_preference(tenant_id, preference_id)

    # --- Credits -----------------------------------------------------------
    async def register_credit(
        self,
        tenant_id: uuid.UUID,
        customer_id: uuid.UUID,
        total_amount: Decimal,
        reference_id: uuid.UUID | None = None,
    ) -> CustomerCredit:
        await self._require_customer(tenant_id, customer_id)
        if total_amount <= 0:
            raise ValidationError("El monto del crédito debe ser positivo.")
        return await self._repo.create_credit(
            CustomerCredit(
                tenant_id=tenant_id,
                customer_id=customer_id,
                total_amount=total_amount,
                reference_id=reference_id,
            )
        )

    async def list_credits(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID
    ) -> list[CustomerCredit]:
        await self._require_customer(tenant_id, customer_id)
        return await self._repo.list_credits(tenant_id, customer_id)

    async def get_credit(
        self, tenant_id: uuid.UUID, credit_id: uuid.UUID
    ) -> CustomerCredit:
        return await self._require_credit(tenant_id, credit_id)

    # --- Credit payments ---------------------------------------------------
    async def register_credit_payment(
        self,
        tenant_id: uuid.UUID,
        credit_id: uuid.UUID,
        amount: Decimal,
        method: str,
        employee_id: uuid.UUID,
    ) -> CustomerCreditPayment:
        credit = await self._require_credit(tenant_id, credit_id)
        await self._require_employee(tenant_id, employee_id)
        if amount <= 0:
            raise ValidationError("El monto del pago debe ser positivo.")
        # A cash settlement enters the drawer. Customer credits carry no branch, so resolve it from
        # the paying employee, require that branch's open session, and post a matching `in` movement
        # atomically. Non-cash methods do not touch the cash session.
        cash_session_id: uuid.UUID | None = None
        branch_id: uuid.UUID | None = None
        if method == "cash":
            branch_id = await self._repo.employee_branch(tenant_id, employee_id)
            cash_session_id = (
                await self._repo.get_open_cash_session_id(tenant_id, branch_id)
                if branch_id is not None
                else None
            )
            if cash_session_id is None:
                raise ConflictError(
                    "No hay sesión de caja abierta en la sucursal del empleado para "
                    "registrar el abono en efectivo."
                )
        payment = await self._repo.create_credit_payment(
            CustomerCreditPayment(
                tenant_id=tenant_id,
                customer_credit_id=credit_id,
                amount=amount,
                method=method,
                employee_id=employee_id,
            ),
            cash_session_id=cash_session_id,
            branch_id=branch_id if cash_session_id is not None else None,
        )
        paid = await self._repo.credit_payments_total(tenant_id, credit_id)
        if paid >= credit.total_amount:
            status = CREDIT_PAID
        elif paid > 0:
            status = CREDIT_PARTIAL
        else:
            status = CREDIT_PENDING
        await self._repo.update_credit(
            tenant_id, credit_id, {"payment_status": status}
        )
        return payment

    async def list_credit_payments(
        self, tenant_id: uuid.UUID, credit_id: uuid.UUID
    ) -> list[CustomerCreditPayment]:
        await self._require_credit(tenant_id, credit_id)
        return await self._repo.list_credit_payments(tenant_id, credit_id)
