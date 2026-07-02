"""Dependency wiring for the Menu API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.menu.application.use_cases.manage_menu import MenuService
from restaurante.modules.menu.infrastructure.repositories import (
    SqlAlchemyMenuRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_menu_service(session: SessionDep) -> MenuService:
    return MenuService(repo=SqlAlchemyMenuRepository(session))


MenuServiceDep = Annotated[MenuService, Depends(get_menu_service)]
