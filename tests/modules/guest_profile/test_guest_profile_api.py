"""Guest profile API: cookie-identified anonymous contact data, coexisting with auth.

The ``guest_token`` cookie is set ``secure`` (production default, ``DEBUG=false`` in
tests), so httpx over http stores but will not resend it. Each test captures the
minted token from the response and re-injects it as a plain (non-secure) cookie so the
round-trip is exercised the way a real https browser would.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.guest_profile.infrastructure.models import GuestProfileModel
from restaurante.shared.database import SessionFactory
from tests.conftest import TEST_EMAIL, TEST_PASSWORD

_COOKIE = "guest_token"
_DOMAIN = "demo.api.local"


def _capture_token(client: AsyncClient, resp: object) -> str:
    """Read the minted token from a response and make the client resend it over http."""
    token = resp.cookies.get(_COOKIE)  # type: ignore[attr-defined]
    assert token, "response should set the guest_token cookie"
    client.cookies.set(_COOKIE, token, domain=_DOMAIN)
    return token


async def _login(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _count_rows() -> int:
    async with SessionFactory() as session:
        rows = (await session.execute(select(GuestProfileModel))).scalars().all()
        return len(rows)


# --- create / update (POST) ------------------------------------------------
async def test_create_sets_cookie_and_persists_row(client: AsyncClient) -> None:
    resp = await client.post(
        "/guest-profile",
        json={"name": "Ana", "address": "Calle 1 #2-3", "phone": "3001234567"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"name": "Ana", "address": "Calle 1 #2-3", "phone": "3001234567"}

    set_cookie = resp.headers.get("set-cookie", "")
    assert f"{_COOKIE}=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Max-Age=31536000" in set_cookie
    assert "samesite=lax" in set_cookie.lower()
    assert "Secure" in set_cookie  # DEBUG=false in tests → production cookie
    assert await _count_rows() == 1


async def test_update_reuses_same_token_no_duplicate(client: AsyncClient) -> None:
    first = await client.post("/guest-profile", json={"name": "Ana"})
    token = _capture_token(client, first)

    second = await client.post(
        "/guest-profile", json={"name": "Ana María", "phone": "3009999999"}
    )
    assert second.status_code == 200, second.text
    assert second.json()["name"] == "Ana María"
    # Same token round-tripped → one row updated, not a second row created.
    assert await _count_rows() == 1
    async with SessionFactory() as session:
        row = (await session.execute(select(GuestProfileModel))).scalar_one()
        assert str(row.token) == token
        assert row.name == "Ana María"
        assert row.phone == "3009999999"


# --- read (GET) ------------------------------------------------------------
async def test_get_without_cookie_returns_null_not_500(client: AsyncClient) -> None:
    resp = await client.get("/guest-profile")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"name": None, "address": None, "phone": None}


async def test_get_unknown_token_returns_null(client: AsyncClient) -> None:
    client.cookies.set(_COOKIE, str(uuid.uuid4()), domain=_DOMAIN)
    resp = await client.get("/guest-profile")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"name": None, "address": None, "phone": None}


async def test_get_returns_saved_profile(client: AsyncClient) -> None:
    created = await client.post(
        "/guest-profile", json={"name": "Ana", "phone": "3001234567"}
    )
    _capture_token(client, created)

    resp = await client.get("/guest-profile")
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Ana"
    assert resp.json()["phone"] == "3001234567"


# --- edit (PATCH) ----------------------------------------------------------
async def test_patch_edits_only_provided_fields(client: AsyncClient) -> None:
    created = await client.post(
        "/guest-profile", json={"name": "Ana", "phone": "3001234567"}
    )
    _capture_token(client, created)

    resp = await client.patch("/guest-profile", json={"phone": "3007654321"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Ana"  # untouched
    assert body["phone"] == "3007654321"  # edited


async def test_patch_without_cookie_is_404(client: AsyncClient) -> None:
    resp = await client.patch("/guest-profile", json={"phone": "3007654321"})
    assert resp.status_code == 404, resp.text


async def test_token_in_query_is_ignored(client: AsyncClient) -> None:
    """A token supplied via query string (not the cookie) must never resolve a profile."""
    created = await client.post("/guest-profile", json={"name": "Ana"})
    token = _capture_token(client, created)
    client.cookies.delete(_COOKIE, domain=_DOMAIN)  # drop the cookie

    resp = await client.get(f"/guest-profile?guest_token={token}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"name": None, "address": None, "phone": None}


# --- claim / merge + coexistence with auth ---------------------------------
async def test_claim_links_profile_to_authenticated_user(client: AsyncClient) -> None:
    created = await client.post("/guest-profile", json={"name": "Ana"})
    token = _capture_token(client, created)

    headers = await _login(client)  # JWT auth works alongside the guest cookie
    resp = await client.post("/guest-profile/claim", headers=headers)
    assert resp.status_code == 200, resp.text

    async with SessionFactory() as session:
        row = (
            await session.execute(
                select(GuestProfileModel).where(GuestProfileModel.token == uuid.UUID(token))
            )
        ).scalar_one()
        assert row.user_id is not None  # linked to the logged-in user


async def test_claim_cannot_touch_another_sessions_profile(client: AsyncClient) -> None:
    # Session A saves a profile (its token never reaches the claimer).
    created = await client.post("/guest-profile", json={"name": "Ana"})
    other_token = _capture_token(client, created)
    client.cookies.delete(_COOKIE, domain=_DOMAIN)

    # A different session claims with its own (absent) cookie.
    headers = await _login(client)
    resp = await client.post("/guest-profile/claim", headers=headers)
    assert resp.status_code == 200, resp.text  # nothing to claim, no error

    async with SessionFactory() as session:
        row = (
            await session.execute(
                select(GuestProfileModel).where(
                    GuestProfileModel.token == uuid.UUID(other_token)
                )
            )
        ).scalar_one()
        assert row.user_id is None  # stranger's profile untouched
