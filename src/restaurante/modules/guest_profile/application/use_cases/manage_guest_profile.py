"""Application service for the Guest Profile module.

Orchestrates the token lifecycle: create-or-update keyed by the cookie token
(minting a token when there is none), a null-safe read, a partial edit, and the
claim/merge that links a saved profile to a real user on login.
"""

from __future__ import annotations

import uuid
from typing import Any

from restaurante.modules.guest_profile.domain.entities import GuestProfile
from restaurante.modules.guest_profile.domain.ports import GuestProfileRepository


class GuestProfileService:
    def __init__(self, repo: GuestProfileRepository) -> None:
        self._repo = repo

    async def get(
        self, tenant_id: uuid.UUID, token: uuid.UUID | None
    ) -> GuestProfile | None:
        """The profile for this cookie token, or ``None`` when absent/unknown.

        Never raises for a missing cookie or a token with no row — the caller
        returns a clean empty payload, not a 500.
        """
        if token is None:
            return None
        return await self._repo.get_by_token(tenant_id, token)

    async def create_or_update(
        self,
        tenant_id: uuid.UUID,
        token: uuid.UUID | None,
        *,
        name: str | None,
        address: str | None,
        phone: str | None,
    ) -> GuestProfile:
        """Upsert the contact data for ``token``, minting one when there is none.

        Returns the saved profile; its ``token`` is what the caller writes back
        to the ``guest_token`` cookie (a fresh one on first save, otherwise the
        same value, which refreshes the cookie's expiry).
        """
        fields: dict[str, Any] = {"name": name, "address": address, "phone": phone}
        if token is not None:
            existing = await self._repo.get_by_token(tenant_id, token)
            if existing is not None:
                updated = await self._repo.update(tenant_id, token, fields)
                assert updated is not None  # just fetched under the same session
                return updated
        # No cookie, or a cookie whose row is gone: create a row for a token.
        new_token = token if token is not None else uuid.uuid4()
        return await self._repo.create(
            GuestProfile(
                tenant_id=tenant_id,
                token=new_token,
                name=name,
                address=address,
                phone=phone,
            )
        )

    async def patch(
        self, tenant_id: uuid.UUID, token: uuid.UUID | None, fields: dict[str, Any]
    ) -> GuestProfile | None:
        """Edit only the provided fields of the cookie's profile.

        Returns ``None`` when there is no cookie or no matching row so the caller
        can answer 404 rather than fabricate a profile.
        """
        if token is None:
            return None
        return await self._repo.update(tenant_id, token, fields)

    async def claim(
        self, tenant_id: uuid.UUID, token: uuid.UUID | None, user_id: uuid.UUID
    ) -> GuestProfile | None:
        """Link the cookie's guest profile to a now-authenticated user.

        Keyed by the caller's own cookie token, so it can never touch another
        session's profile. Returns ``None`` when there is nothing to claim.
        """
        if token is None:
            return None
        return await self._repo.link_user(tenant_id, token, user_id)
