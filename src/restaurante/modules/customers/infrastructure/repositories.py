"""Persistence adapter for the Customers module over SQLAlchemy async.

Each write commits its own unit of work and filters explicitly by ``tenant_id``.
Creating a customer inserts the backing ``person`` (global) and the ``customer``
in one transaction; unique violations are translated to ``ConflictError``.
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
from restaurante.modules.customers.domain.entities import (
    Customer,
    CustomerCredit,
    CustomerCreditPayment,
    CustomerPreference,
)
from restaurante.modules.customers.infrastructure.models import (
    CustomerCreditModel,
    CustomerCreditPaymentModel,
    CustomerModel,
    CustomerPreferenceModel,
)
from restaurante.modules.identity.infrastructure.models import PersonModel, UserModel
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.domain.errors import ConflictError


def _customer(m: CustomerModel, person: PersonModel | None = None) -> Customer:
    return Customer(
        id=m.id,
        tenant_id=m.tenant_id,
        person_id=m.person_id,
        user_id=m.user_id,
        is_active=m.is_active,
        total_spent=m.total_spent,
        order_count=m.order_count,
        last_purchase_at=m.last_purchase_at,
        registered_at=m.registered_at,
        first_name=person.first_name if person else None,
        last_name=person.last_name if person else None,
        document_number=person.document_number if person else None,
        phone=person.phone if person else None,
        email=person.email if person else None,
    )


def _preference(m: CustomerPreferenceModel) -> CustomerPreference:
    return CustomerPreference(
        id=m.id,
        tenant_id=m.tenant_id,
        customer_id=m.customer_id,
        key=m.key,
        value=m.value,
    )


def _credit(m: CustomerCreditModel) -> CustomerCredit:
    return CustomerCredit(
        id=m.id,
        tenant_id=m.tenant_id,
        customer_id=m.customer_id,
        total_amount=m.total_amount,
        payment_status=m.payment_status,
        reference_id=m.reference_id,
    )


def _credit_payment(m: CustomerCreditPaymentModel) -> CustomerCreditPayment:
    return CustomerCreditPayment(
        id=m.id,
        tenant_id=m.tenant_id,
        customer_credit_id=m.customer_credit_id,
        amount=m.amount,
        method=m.method,
        employee_id=m.employee_id,
        paid_at=m.paid_at,
    )


class SqlAlchemyCustomersRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reference existence checks ----------------------------------------
    async def user_exists(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        stmt = select(UserModel.id).where(
            UserModel.id == user_id, UserModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def employee_exists(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool:
        stmt = select(EmployeeModel.id).where(
            EmployeeModel.id == employee_id, EmployeeModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Customers ---------------------------------------------------------
    async def create_customer(
        self, person_fields: dict[str, Any], customer: Customer
    ) -> Customer:
        person = PersonModel(**person_fields)
        self._session.add(person)
        await self._session.flush()
        model = CustomerModel(
            tenant_id=customer.tenant_id,
            person_id=person.id,
            user_id=customer.user_id,
            is_active=customer.is_active,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("Ya existe un cliente para esa persona/usuario.") from exc
        await self._session.refresh(model)
        # The person was just created in this session; reuse it for the read fields.
        return _customer(model, person)

    # Fetch the backing person explicitly (async-safe; avoids lazy relationship loads).
    async def _person_for(self, person_id: uuid.UUID) -> PersonModel | None:
        stmt = select(PersonModel).where(PersonModel.id == person_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def _get_customer_model(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID
    ) -> CustomerModel | None:
        stmt = select(CustomerModel).where(
            CustomerModel.id == customer_id, CustomerModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_customer(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID
    ) -> Customer | None:
        model = await self._get_customer_model(tenant_id, customer_id)
        if model is None:
            return None
        return _customer(model, await self._person_for(model.person_id))

    async def list_customers(
        self, tenant_id: uuid.UUID, *, active: bool | None = None
    ) -> list[Customer]:
        # Join the person so each customer carries its identity (one query, no N+1).
        stmt = (
            select(CustomerModel, PersonModel)
            .join(PersonModel, CustomerModel.person_id == PersonModel.id)
            .where(CustomerModel.tenant_id == tenant_id)
        )
        if active is not None:
            stmt = stmt.where(CustomerModel.is_active.is_(active))
        stmt = stmt.order_by(CustomerModel.registered_at.desc())
        rows = (await self._session.execute(stmt)).all()
        return [_customer(c, p) for c, p in rows]

    async def update_customer(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID, fields: dict[str, Any]
    ) -> Customer | None:
        model = await self._get_customer_model(tenant_id, customer_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _customer(model, await self._person_for(model.person_id))

    # --- Preferences -------------------------------------------------------
    async def set_preference(
        self, preference: CustomerPreference
    ) -> CustomerPreference:
        model = CustomerPreferenceModel(
            tenant_id=preference.tenant_id,
            customer_id=preference.customer_id,
            key=preference.key,
            value=preference.value,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _preference(model)

    async def list_preferences(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID
    ) -> list[CustomerPreference]:
        stmt = select(CustomerPreferenceModel).where(
            CustomerPreferenceModel.tenant_id == tenant_id,
            CustomerPreferenceModel.customer_id == customer_id,
        )
        return [_preference(m) for m in (await self._session.execute(stmt)).scalars()]

    async def delete_preference(
        self, tenant_id: uuid.UUID, preference_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            sql_delete(CustomerPreferenceModel).where(
                CustomerPreferenceModel.tenant_id == tenant_id,
                CustomerPreferenceModel.id == preference_id,
            )
        )
        await self._session.commit()

    # --- Credits -----------------------------------------------------------
    async def create_credit(self, credit: CustomerCredit) -> CustomerCredit:
        model = CustomerCreditModel(
            tenant_id=credit.tenant_id,
            customer_id=credit.customer_id,
            total_amount=credit.total_amount,
            payment_status=credit.payment_status,
            reference_id=credit.reference_id,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _credit(model)

    async def _get_credit_model(
        self, tenant_id: uuid.UUID, credit_id: uuid.UUID
    ) -> CustomerCreditModel | None:
        stmt = select(CustomerCreditModel).where(
            CustomerCreditModel.id == credit_id,
            CustomerCreditModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_credit(
        self, tenant_id: uuid.UUID, credit_id: uuid.UUID
    ) -> CustomerCredit | None:
        model = await self._get_credit_model(tenant_id, credit_id)
        return _credit(model) if model else None

    async def list_credits(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID
    ) -> list[CustomerCredit]:
        stmt = (
            select(CustomerCreditModel)
            .where(
                CustomerCreditModel.tenant_id == tenant_id,
                CustomerCreditModel.customer_id == customer_id,
            )
            .order_by(CustomerCreditModel.created_at.desc())
        )
        return [_credit(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_credit(
        self, tenant_id: uuid.UUID, credit_id: uuid.UUID, fields: dict[str, Any]
    ) -> CustomerCredit | None:
        model = await self._get_credit_model(tenant_id, credit_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _credit(model)

    # --- Cash drawer (fiado ↔ cash integration) ----------------------------
    async def employee_branch(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> uuid.UUID | None:
        stmt = select(EmployeeModel.branch_id).where(
            EmployeeModel.id == employee_id, EmployeeModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def get_open_cash_session_id(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> uuid.UUID | None:
        stmt = select(CashSessionModel.id).where(
            CashSessionModel.tenant_id == tenant_id,
            CashSessionModel.branch_id == branch_id,
            CashSessionModel.status == "open",
        )
        return (await self._session.execute(stmt)).scalars().first()

    # --- Credit payments ---------------------------------------------------
    async def create_credit_payment(
        self,
        payment: CustomerCreditPayment,
        *,
        cash_session_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
    ) -> CustomerCreditPayment:
        """Persist the settlement and, for cash, a matching drawer `in` movement atomically."""
        model = CustomerCreditPaymentModel(
            tenant_id=payment.tenant_id,
            customer_credit_id=payment.customer_credit_id,
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
                    type="in",
                    concept="credit_payment",
                    amount=payment.amount,
                    method=payment.method,
                    reference_id=payment.customer_credit_id,
                )
            )
        await self._session.commit()
        await self._session.refresh(model)
        return _credit_payment(model)

    async def list_credit_payments(
        self, tenant_id: uuid.UUID, credit_id: uuid.UUID
    ) -> list[CustomerCreditPayment]:
        stmt = (
            select(CustomerCreditPaymentModel)
            .where(
                CustomerCreditPaymentModel.tenant_id == tenant_id,
                CustomerCreditPaymentModel.customer_credit_id == credit_id,
            )
            .order_by(CustomerCreditPaymentModel.paid_at)
        )
        return [
            _credit_payment(m) for m in (await self._session.execute(stmt)).scalars()
        ]

    async def credit_payments_total(
        self, tenant_id: uuid.UUID, credit_id: uuid.UUID
    ) -> Decimal:
        stmt = select(
            func.coalesce(func.sum(CustomerCreditPaymentModel.amount), 0)
        ).where(
            CustomerCreditPaymentModel.tenant_id == tenant_id,
            CustomerCreditPaymentModel.customer_credit_id == credit_id,
        )
        return Decimal(str((await self._session.execute(stmt)).scalar_one()))
