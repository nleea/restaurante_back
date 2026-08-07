"""Resolver la mesa detrás del QR: sede y mesa vienen de la RUTA, y leer no ocupa nada."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.orders.infrastructure.models import DiningTableModel
from restaurante.shared.database import SessionFactory
from tests.modules._cash import seed_open_cash_session
from tests.modules.storefront._seed import (
    seed_dining_table,
    seed_menu,
    seed_primary_branch,
)


async def _status(table_id: uuid.UUID) -> str:
    async with SessionFactory() as session:
        return (
            await session.execute(
                select(DiningTableModel.status).where(DiningTableModel.id == table_id)
            )
        ).scalar_one()


async def test_resolves_the_table_behind_its_code(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch(code="centro")
    await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)
    table_id = await seed_dining_table(branch_id, number="5", code="M5CODE")

    resp = await client.get("/storefront/centro/tables/M5CODE")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(table_id)
    assert body["number"] == "5"
    assert body["branchId"] == str(branch_id)
    assert body["canOrderNow"] is True


async def test_resolving_does_not_occupy_the_table(client: AsyncClient) -> None:
    """Quien escanea de paso no puede dejar una mesa marcada como ocupada sin nadie en ella."""
    branch_id = await seed_primary_branch(code="centro")
    await seed_open_cash_session(branch_id)
    table_id = await seed_dining_table(branch_id, code="M5CODE")
    assert await _status(table_id) == "free"

    assert (await client.get("/storefront/centro/tables/M5CODE")).status_code == 200

    assert await _status(table_id) == "free"


async def test_rejects_a_table_code_from_another_branch(client: AsyncClient) -> None:
    """El código sólo es único DENTRO de su sede.

    Aceptarlo cruzado sacaría la comida en otra cocina.
    """
    centro = await seed_primary_branch(code="centro")
    norte = await seed_primary_branch(is_primary=False, code="norte")
    await seed_dining_table(centro, number="5", code="M5CODE")
    await seed_dining_table(norte, number="9", code="N9CODE")

    resp = await client.get("/storefront/centro/tables/N9CODE")

    assert resp.status_code == 404
    assert resp.json()["code"] == "table_not_found"


async def test_rejects_an_unknown_code(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch(code="centro")
    await seed_dining_table(branch_id, code="M5CODE")

    resp = await client.get("/storefront/centro/tables/NOPE99")

    assert resp.status_code == 404
    assert resp.json()["code"] == "table_not_found"


async def test_rejects_a_deactivated_table(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch(code="centro")
    await seed_dining_table(branch_id, code="M5CODE", is_active=False)

    resp = await client.get("/storefront/centro/tables/M5CODE")

    assert resp.status_code == 404
    assert resp.json()["code"] == "table_not_found"


async def test_unknown_branch_is_a_branch_404_not_a_table_one(
    client: AsyncClient,
) -> None:
    """El front distingue "esa sede no existe" de "ese código no es de ninguna mesa"."""
    branch_id = await seed_primary_branch(code="centro")
    await seed_dining_table(branch_id, code="M5CODE")

    resp = await client.get("/storefront/fantasma/tables/M5CODE")

    assert resp.status_code == 404
    assert resp.json()["code"] == "branch_not_found"


async def test_closed_caja_is_reported_without_failing(client: AsyncClient) -> None:
    """Se dice ANTES del carrito. La mesa resuelve igual; lo que cambia es lo que se puede hacer."""
    branch_id = await seed_primary_branch(code="centro")
    await seed_menu(branch_id)
    await seed_dining_table(branch_id, code="M5CODE")  # sin sesión de caja abierta

    resp = await client.get("/storefront/centro/tables/M5CODE")

    assert resp.status_code == 200, resp.text
    assert resp.json()["canOrderNow"] is False
    assert resp.json()["number"] == "5"
