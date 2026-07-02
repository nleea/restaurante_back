"""Dependency wiring for the Customers API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.customers.application.use_cases.manage_customers import (
    CustomerService,
)
from restaurante.modules.customers.infrastructure.repositories import (
    SqlAlchemyCustomersRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_customer_service(session: SessionDep) -> CustomerService:
    return CustomerService(repo=SqlAlchemyCustomersRepository(session))


CustomerServiceDep = Annotated[CustomerService, Depends(get_customer_service)]
