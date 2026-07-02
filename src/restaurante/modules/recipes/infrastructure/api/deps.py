"""Dependency wiring for the Recipes API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.recipes.application.use_cases.manage_recipes import (
    RecipesService,
)
from restaurante.modules.recipes.infrastructure.repositories import (
    SqlAlchemyRecipesRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def get_recipes_service(session: SessionDep) -> RecipesService:
    return RecipesService(repo=SqlAlchemyRecipesRepository(session))


RecipesServiceDep = Annotated[RecipesService, Depends(get_recipes_service)]
