"""Integration tests for the Menu appearance API (persistence + RBAC + tenancy)."""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import func, select

from restaurante.modules.identity.infrastructure.models import UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.modules.menu.application.use_cases.manage_appearance import (
    default_appearance_config,
)
from restaurante.modules.menu.infrastructure.models import MenuAppearanceModel
from restaurante.modules.menu.infrastructure.repositories import (
    SqlAlchemyMenuRepository,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import TenantModel
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


async def _demo_ids() -> tuple[uuid.UUID, uuid.UUID]:
    async with SessionFactory() as session:
        tenant = (
            await session.execute(select(TenantModel).where(TenantModel.slug == "demo"))
        ).scalar_one()
        user = (
            await session.execute(
                select(UserModel).where(UserModel.email == TEST_EMAIL)
            )
        ).scalar_one()
        return tenant.id, user.id


async def _assign_role(role_name: str) -> None:
    tenant_id, user_id = await _demo_ids()
    async with SessionFactory() as session:
        roles = await seed_rbac(session)
        await session.commit()
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles[role_name].id
        )


async def _login(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _valid_config() -> dict[str, Any]:
    """A valid config derived from the default, with a couple of edits."""
    config = deepcopy(default_appearance_config())
    config["brand"]["restaurantName"] = "La Cevichería del Cabo"
    config["theme"]["primaryColor"] = "#b5432b"
    return config


# --- GET default ------------------------------------------------------------
async def test_get_appearance_returns_default_before_save(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)

    resp = await client.get("/menu/appearance", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Shape mirrors the frontend default.
    assert body == default_appearance_config()
    assert body["brand"]["restaurantName"] == ""
    assert body["theme"]["fontFamily"] == "Poppins"
    # The 4 presentation blocks start hidden.
    hidden = {b["id"] for b in body["blocks"] if not b["visible"]}
    assert hidden == {"promo", "hours", "gallery", "testimonials"}


# --- PUT create then overwrite (single row) --------------------------------
async def test_put_creates_then_overwrites_single_row(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    tenant_id, _ = await _demo_ids()

    first = await client.put(
        "/menu/appearance", headers=headers, json=_valid_config()
    )
    assert first.status_code == 200, first.text
    assert first.json()["brand"]["restaurantName"] == "La Cevichería del Cabo"

    # GET now returns the saved config, not the default.
    saved = await client.get("/menu/appearance", headers=headers)
    assert saved.json()["theme"]["primaryColor"] == "#b5432b"

    # A second PUT overwrites in place — still exactly one row for the tenant.
    updated = _valid_config()
    updated["brand"]["restaurantName"] = "Nuevo Nombre"
    second = await client.put("/menu/appearance", headers=headers, json=updated)
    assert second.status_code == 200
    assert second.json()["brand"]["restaurantName"] == "Nuevo Nombre"

    async with SessionFactory() as session:
        count = (
            await session.execute(
                select(func.count(MenuAppearanceModel.id)).where(
                    MenuAppearanceModel.tenant_id == tenant_id
                )
            )
        ).scalar_one()
    assert count == 1


# --- Tenancy isolation ------------------------------------------------------
async def test_appearance_isolated_by_tenant(setup_db: None) -> None:
    tenant_a, _ = await _demo_ids()
    tenant_b = uuid.uuid4()
    config_a = _valid_config()
    config_a["brand"]["restaurantName"] = "Tenant A"

    async with SessionFactory() as session:
        repo = SqlAlchemyMenuRepository(session)
        await repo.upsert_appearance(tenant_a, config_a)

        assert await repo.get_appearance(tenant_b) is None
        stored = await repo.get_appearance(tenant_a)
        assert stored is not None
        assert stored["brand"]["restaurantName"] == "Tenant A"


# --- RBAC -------------------------------------------------------------------
async def test_get_appearance_without_menu_read_403(client: AsyncClient) -> None:
    headers = await _login(client)  # demo user has no roles
    resp = await client.get("/menu/appearance", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


async def test_put_appearance_without_menu_manage_403(client: AsyncClient) -> None:
    await _assign_role("cashier")  # read-only role
    headers = await _login(client)
    resp = await client.put(
        "/menu/appearance", headers=headers, json=_valid_config()
    )
    assert resp.status_code == 403


# --- Validation -------------------------------------------------------------
async def test_put_malformed_payload_422(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)

    resp = await client.put(
        "/menu/appearance",
        headers=headers,
        json={"theme": "not-an-object"},
    )
    assert resp.status_code == 422
