"""Shared test helper: seed an OPEN cash session for a branch.

Order creation (``OrderService.open_order``) now refuses to open an order when the
branch has no open cash session, raising ``CashClosedError``. Every happy-path test
that creates an order must therefore have an open ``cash_sessions`` row for its branch
before the first order is created. This helper provisions one directly via
``SessionFactory`` (no HTTP, no RBAC), mirroring the direct-DB seeding style used by
``tests/modules/storefront/_seed.py``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from restaurante.modules.cash.infrastructure.models import CashSessionModel
from restaurante.modules.identity.infrastructure.models import (
    PersonModel,
    RoleModel,
    UserModel,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import BranchModel


async def _existing_employee_id(
    session, tenant_id: uuid.UUID
) -> uuid.UUID | None:
    stmt = (
        select(EmployeeModel.id)
        .where(EmployeeModel.tenant_id == tenant_id)
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _make_employee(
    session, tenant_id: uuid.UUID, branch_id: uuid.UUID
) -> uuid.UUID:
    """Minimal person + user + role + employee, mirroring resolve_system_employee."""
    person = PersonModel(first_name="Caja", last_name="Seed")
    session.add(person)
    await session.flush()

    user = UserModel(
        tenant_id=tenant_id,
        email=f"caja-seed-{uuid.uuid4().hex[:8]}@demo.com",
        hashed_password="x",
        name="Caja Seed",
        person_id=person.id,
        is_active=True,
    )
    session.add(user)
    await session.flush()

    role_id = (
        await session.execute(
            select(RoleModel.id).where(RoleModel.tenant_id == tenant_id).limit(1)
        )
    ).scalar_one_or_none()
    if role_id is None:
        role = RoleModel(tenant_id=tenant_id, name="Sistema", is_active=True)
        session.add(role)
        await session.flush()
        role_id = role.id

    employee = EmployeeModel(
        tenant_id=tenant_id,
        branch_id=branch_id,
        person_id=person.id,
        user_id=user.id,
        role_id=role_id,
        is_active=True,
    )
    session.add(employee)
    await session.flush()
    return employee.id


async def seed_open_cash_session(
    branch_id: uuid.UUID, opened_by_employee_id: uuid.UUID | None = None
) -> uuid.UUID:
    """Open a cash session for ``branch_id`` and return its id.

    Reuses an existing employee of the branch's tenant when ``opened_by_employee_id``
    is not supplied, creating a minimal one only when the tenant has none.
    """
    async with SessionFactory() as session:
        tenant_id = (
            await session.execute(
                select(BranchModel.tenant_id).where(BranchModel.id == branch_id)
            )
        ).scalar_one()

        employee_id = opened_by_employee_id
        if employee_id is None:
            employee_id = await _existing_employee_id(session, tenant_id)
        if employee_id is None:
            employee_id = await _make_employee(session, tenant_id, branch_id)

        cash_session = CashSessionModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            opened_by_employee_id=employee_id,
            opening_amount=Decimal("0"),
            status="open",
        )
        session.add(cash_session)
        await session.commit()
        await session.refresh(cash_session)
        return cash_session.id
