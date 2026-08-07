"""Guest Profile API: cookie-identified anonymous customer contact data.

Public read/create/update (tenant by subdomain only, like the storefront). The
opaque token is carried in a dedicated ``guest_token`` cookie and is ALWAYS read
from that cookie — never a query parameter or request body. ``/claim`` is the one
authenticated endpoint: it links the cookie's profile to the current user.

The cookie is ``httponly`` + ``samesite=lax`` with a one-year max age. ``secure``
follows the environment (on in production, off under ``debug`` so local http
dev can still set it). Coexists with the real-user JWT auth, which uses the
``Authorization`` header and no cookies, so there is no cookie/header collision.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Cookie, Response

from restaurante.modules.guest_profile.infrastructure.api.deps import (
    GuestProfileServiceDep,
    TenantDep,
)
from restaurante.modules.guest_profile.infrastructure.api.schemas import (
    GuestProfileRead,
    GuestProfileWrite,
)
from restaurante.modules.identity.infrastructure.api.deps import CurrentUserDep
from restaurante.shared.config import get_settings
from restaurante.shared.domain.errors import NotFoundError

router = APIRouter(prefix="/guest-profile", tags=["guest-profile"])

_COOKIE = "guest_token"
_MAX_AGE = 60 * 60 * 24 * 365  # one year

GuestTokenCookie = Annotated[str | None, Cookie(alias=_COOKIE)]


def _parse_token(raw: str | None) -> uuid.UUID | None:
    """Cookie string → UUID, or ``None`` for a missing/malformed value."""
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except (ValueError, TypeError):
        return None


def _set_cookie(response: Response, token: uuid.UUID) -> None:
    response.set_cookie(
        key=_COOKIE,
        value=str(token),
        httponly=True,
        secure=not get_settings().debug,
        samesite="lax",
        max_age=_MAX_AGE,
    )


@router.post("", response_model=GuestProfileRead)
async def upsert_guest_profile(
    payload: GuestProfileWrite,
    response: Response,
    service: GuestProfileServiceDep,
    tenant_id: TenantDep,
    guest_token: GuestTokenCookie = None,
) -> GuestProfileRead:
    """Create the profile (minting a token) or update the cookie's existing one."""
    profile = await service.create_or_update(
        tenant_id,
        _parse_token(guest_token),
        name=payload.name,
        address=payload.address,
        phone=payload.phone,
    )
    _set_cookie(response, profile.token)
    return GuestProfileRead.from_entity(profile)


@router.get("", response_model=GuestProfileRead)
async def read_guest_profile(
    service: GuestProfileServiceDep,
    tenant_id: TenantDep,
    guest_token: GuestTokenCookie = None,
) -> GuestProfileRead:
    """The cookie's saved profile, or a clean empty payload (never a 500)."""
    profile = await service.get(tenant_id, _parse_token(guest_token))
    return GuestProfileRead.from_entity(profile)


@router.patch("", response_model=GuestProfileRead)
async def edit_guest_profile(
    payload: GuestProfileWrite,
    service: GuestProfileServiceDep,
    tenant_id: TenantDep,
    guest_token: GuestTokenCookie = None,
) -> GuestProfileRead:
    """Edit only the provided fields of the cookie's profile."""
    profile = await service.patch(
        tenant_id,
        _parse_token(guest_token),
        payload.model_dump(exclude_unset=True),
    )
    if profile is None:
        raise NotFoundError("No hay un perfil de invitado para editar.")
    return GuestProfileRead.from_entity(profile)


@router.post("/claim", response_model=GuestProfileRead)
async def claim_guest_profile(
    response: Response,
    current_user: CurrentUserDep,
    service: GuestProfileServiceDep,
    tenant_id: TenantDep,
    guest_token: GuestTokenCookie = None,
) -> GuestProfileRead:
    """Link the cookie's guest profile to the authenticated user, then drop the cookie.

    Keyed by the caller's own cookie, so it can only ever claim the caller's own
    guest profile. Clearing the cookie hands precedence to the real account.
    """
    profile = await service.claim(tenant_id, _parse_token(guest_token), current_user.id)
    response.delete_cookie(_COOKIE)
    return GuestProfileRead.from_entity(profile)
