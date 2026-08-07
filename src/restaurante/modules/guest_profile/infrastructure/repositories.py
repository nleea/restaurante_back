"""Persistence adapter for the Guest Profile module over SQLAlchemy async.

Every read and write filters explicitly by ``tenant_id`` (in addition to the
automatic tenancy filter) so a token minted under one tenant can never resolve
under another. Each write commits its own unit of work.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.guest_profile.domain.entities import GuestProfile
from restaurante.modules.guest_profile.infrastructure.models import GuestProfileModel

# Only these columns may be written from a request payload.
_EDITABLE = ("name", "address", "phone")


def _entity(m: GuestProfileModel) -> GuestProfile:
    return GuestProfile(
        id=m.id,
        tenant_id=m.tenant_id,
        token=m.token,
        name=m.name,
        address=m.address,
        phone=m.phone,
        user_id=m.user_id,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class SqlAlchemyGuestProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _model_for(
        self, tenant_id: uuid.UUID, token: uuid.UUID
    ) -> GuestProfileModel | None:
        stmt = select(GuestProfileModel).where(
            GuestProfileModel.token == token,
            GuestProfileModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_token(
        self, tenant_id: uuid.UUID, token: uuid.UUID
    ) -> GuestProfile | None:
        model = await self._model_for(tenant_id, token)
        return _entity(model) if model else None

    async def create(self, profile: GuestProfile) -> GuestProfile:
        model = GuestProfileModel(
            tenant_id=profile.tenant_id,
            token=profile.token,
            name=profile.name,
            address=profile.address,
            phone=profile.phone,
            user_id=profile.user_id,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _entity(model)

    async def update(
        self, tenant_id: uuid.UUID, token: uuid.UUID, fields: dict[str, Any]
    ) -> GuestProfile | None:
        model = await self._model_for(tenant_id, token)
        if model is None:
            return None
        for key, value in fields.items():
            if key in _EDITABLE:
                setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _entity(model)

    async def link_user(
        self, tenant_id: uuid.UUID, token: uuid.UUID, user_id: uuid.UUID
    ) -> GuestProfile | None:
        model = await self._model_for(tenant_id, token)
        if model is None:
            return None
        model.user_id = user_id
        await self._session.commit()
        await self._session.refresh(model)
        return _entity(model)
