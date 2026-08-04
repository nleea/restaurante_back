"""Public storefront appearance endpoint: unauthenticated, tenant by subdomain."""

from __future__ import annotations

from httpx import AsyncClient

from restaurante.modules.menu.application.use_cases.manage_appearance import (
    AppearanceService,
    default_appearance_config,
)
from restaurante.modules.menu.infrastructure.repositories import (
    SqlAlchemyMenuRepository,
)
from restaurante.shared.database import SessionFactory
from tests.modules.storefront._seed import demo_tenant_id


async def test_appearance_unauthenticated_returns_default(client: AsyncClient) -> None:
    resp = await client.get("/storefront/appearance")
    assert resp.status_code == 200
    body = resp.json()
    default = default_appearance_config()
    assert body["theme"]["primaryColor"] == default["theme"]["primaryColor"]
    assert body["brand"]["restaurantName"] == default["brand"]["restaurantName"]


async def test_appearance_unauthenticated_returns_saved(client: AsyncClient) -> None:
    tenant_id = await demo_tenant_id()
    config = default_appearance_config()
    config["brand"]["restaurantName"] = "La Cevichería del Cabo"
    config["theme"]["primaryColor"] = "#b5432b"
    async with SessionFactory() as session:
        await AppearanceService(SqlAlchemyMenuRepository(session)).save_appearance(
            tenant_id, config
        )

    resp = await client.get("/storefront/appearance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["brand"]["restaurantName"] == "La Cevichería del Cabo"
    assert body["theme"]["primaryColor"] == "#b5432b"
