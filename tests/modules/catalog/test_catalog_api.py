"""Integration tests for the Catalog API (countries, cities, units, RBAC)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.identity.infrastructure.models import UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
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


async def _assign_role(role_name: str) -> uuid.UUID:
    tenant_id, user_id = await _demo_ids()
    async with SessionFactory() as session:
        roles = await seed_rbac(session)
        await session.commit()
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles[role_name].id
        )
        return roles[role_name].id


async def _login(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# --- Countries + cities -----------------------------------------------------
async def test_country_city_flow(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)

    country = await client.post(
        "/catalog/countries",
        headers=headers,
        json={"name": "Colombia", "iso_code": "CO"},
    )
    assert country.status_code == 201, country.text
    country_id = country.json()["id"]

    dup = await client.post(
        "/catalog/countries",
        headers=headers,
        json={"name": "Colombia dup", "iso_code": "CO"},
    )
    assert dup.status_code == 409

    city = await client.post(
        "/catalog/cities",
        headers=headers,
        json={"country_id": country_id, "name": "Bogotá", "state_province": "Cundinamarca"},
    )
    assert city.status_code == 201
    cities = await client.get(
        "/catalog/cities", headers=headers, params={"country_id": country_id}
    )
    assert len(cities.json()) == 1


async def test_city_unknown_country_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    resp = await client.post(
        "/catalog/cities",
        headers=headers,
        json={"country_id": str(uuid.uuid4()), "name": "Nowhere"},
    )
    assert resp.status_code == 404


# --- Units of measure -------------------------------------------------------
async def test_unit_base_and_derived(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)

    base = await client.post(
        "/catalog/units", headers=headers, json={"name": "gram", "abbreviation": "g"}
    )
    assert base.status_code == 201
    base_id = base.json()["id"]
    assert base.json()["base_unit_id"] is None

    derived = await client.post(
        "/catalog/units",
        headers=headers,
        json={
            "name": "kilogram",
            "abbreviation": "kg",
            "base_unit_id": base_id,
            "conversion_factor": "1000",
        },
    )
    assert derived.status_code == 201
    assert derived.json()["base_unit_id"] == base_id


async def test_unit_base_factor_mismatch_422(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    base = await client.post(
        "/catalog/units", headers=headers, json={"name": "liter", "abbreviation": "L"}
    )
    base_id = base.json()["id"]
    # base_unit_id without conversion_factor -> 422
    resp = await client.post(
        "/catalog/units",
        headers=headers,
        json={"name": "ml", "abbreviation": "ml", "base_unit_id": base_id},
    )
    assert resp.status_code == 422


async def test_unit_unknown_base_404(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    resp = await client.post(
        "/catalog/units",
        headers=headers,
        json={
            "name": "x",
            "abbreviation": "x",
            "base_unit_id": str(uuid.uuid4()),
            "conversion_factor": "10",
        },
    )
    assert resp.status_code == 404


async def test_unit_self_reference_422(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    unit = await client.post(
        "/catalog/units", headers=headers, json={"name": "unit", "abbreviation": "u"}
    )
    unit_id = unit.json()["id"]
    resp = await client.patch(
        f"/catalog/units/{unit_id}",
        headers=headers,
        json={"base_unit_id": unit_id, "conversion_factor": "1"},
    )
    assert resp.status_code == 422


# --- RBAC / global ----------------------------------------------------------
async def test_requires_permission_without_role(client: AsyncClient) -> None:
    headers = await _login(client)
    resp = await client.get("/catalog/units", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "authorization_error"


async def test_catalog_is_global_across_tenants(client: AsyncClient) -> None:
    # A unit created under the demo tenant is visible when listing (global table).
    await _assign_role("admin")
    headers = await _login(client)
    await client.post(
        "/catalog/units", headers=headers, json={"name": "piece", "abbreviation": "pc"}
    )
    units = await client.get("/catalog/units", headers=headers)
    assert any(u["abbreviation"] == "pc" for u in units.json())
