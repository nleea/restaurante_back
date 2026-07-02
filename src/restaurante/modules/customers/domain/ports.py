"""Ports (interfaces) of the Customers module."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Protocol

from restaurante.modules.customers.domain.entities import (
    Customer,
    CustomerCredit,
    CustomerCreditPayment,
    CustomerPreference,
)


class CustomersRepository(Protocol):
    # --- Reference existence checks ----------------------------------------
    async def user_exists(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> bool: ...

    async def employee_exists(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool: ...

    # --- Customers ---------------------------------------------------------
    async def create_customer(
        self, person_fields: dict[str, Any], customer: Customer
    ) -> Customer: ...

    async def get_customer(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID
    ) -> Customer | None: ...

    async def list_customers(
        self, tenant_id: uuid.UUID, *, active: bool | None = None
    ) -> list[Customer]: ...

    async def update_customer(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID, fields: dict[str, Any]
    ) -> Customer | None: ...

    # --- Preferences -------------------------------------------------------
    async def set_preference(
        self, preference: CustomerPreference
    ) -> CustomerPreference: ...

    async def list_preferences(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID
    ) -> list[CustomerPreference]: ...

    async def delete_preference(
        self, tenant_id: uuid.UUID, preference_id: uuid.UUID
    ) -> None: ...

    # --- Credits -----------------------------------------------------------
    async def create_credit(self, credit: CustomerCredit) -> CustomerCredit: ...

    async def get_credit(
        self, tenant_id: uuid.UUID, credit_id: uuid.UUID
    ) -> CustomerCredit | None: ...

    async def list_credits(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID
    ) -> list[CustomerCredit]: ...

    async def update_credit(
        self, tenant_id: uuid.UUID, credit_id: uuid.UUID, fields: dict[str, Any]
    ) -> CustomerCredit | None: ...

    # --- Credit payments ---------------------------------------------------
    async def employee_branch(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> uuid.UUID | None: ...

    async def get_open_cash_session_id(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> uuid.UUID | None: ...

    async def create_credit_payment(
        self,
        payment: CustomerCreditPayment,
        *,
        cash_session_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
    ) -> CustomerCreditPayment: ...

    async def list_credit_payments(
        self, tenant_id: uuid.UUID, credit_id: uuid.UUID
    ) -> list[CustomerCreditPayment]: ...

    async def credit_payments_total(
        self, tenant_id: uuid.UUID, credit_id: uuid.UUID
    ) -> Decimal: ...
