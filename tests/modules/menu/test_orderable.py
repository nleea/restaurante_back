"""Qué se puede pedir hoy en una sede, en una petición.

Este endpoint nació de un hueco descubierto implementando `server-prices-order-lines`: la pantalla
de comanda pedía los productos, luego un endpoint de precios POR PRODUCTO y otro de variantes POR
PRODUCTO — unas 81 peticiones antes de que el mesero pudiera tocar nada.

Dos propiedades lo sostienen:

1. **Sólo aparece lo vendible.** Un producto sin precio en esa sede lo rechaza `add_item`, así que
   ofrecerlo como mosaico sería ofrecer algo que al tocarlo da error.
2. **El precio del mosaico es el que se cobra.** Viene compuesto (sede + recargo), no recompuesto en
   el cliente: dos fórmulas para el mismo número es el bug que el change cerró.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient

from tests.modules._cash import seed_open_cash_session
from tests.modules._menu import price_variant_for_branch
from tests.modules.orders.test_orders_api import (
    _assign_role,
    _create_branch,
    _create_employee,
    _create_variant,
    _login,
)

PRICE = Decimal("25000.00")


async def _orderable(
    client: AsyncClient, headers: dict[str, str], branch_id: uuid.UUID
) -> list[dict]:
    resp = await client.get(
        "/menu/orderable", headers=headers, params={"branch_id": str(branch_id)}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- Sólo lo vendible -------------------------------------------------------
async def test_a_priced_product_with_an_active_variant_is_orderable(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch(code=f"B{uuid.uuid4().hex[:6]}")
    variant_id = await _create_variant(name="Grande")
    await price_variant_for_branch(variant_id, branch_id, PRICE)

    products = await _orderable(client, headers, branch_id)

    assert len(products) == 1
    assert products[0]["name"] == "Classic Burger"
    assert [v["name"] for v in products[0]["variants"]] == ["Grande"]


async def test_a_product_without_a_branch_price_does_not_appear(
    client: AsyncClient,
) -> None:
    """No se ofrece lo que `add_item` rechazaría: un mosaico que da error es peor que no estar."""
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch(code=f"B{uuid.uuid4().hex[:6]}")
    await _create_variant()  # sin precio

    assert await _orderable(client, headers, branch_id) == []


async def test_a_price_in_another_branch_does_not_make_it_orderable(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    priced = await _create_branch(code=f"A{uuid.uuid4().hex[:6]}")
    other = await _create_branch(code=f"B{uuid.uuid4().hex[:6]}")
    variant_id = await _create_variant()
    await price_variant_for_branch(variant_id, priced, PRICE)

    assert await _orderable(client, headers, other) == []
    assert len(await _orderable(client, headers, priced)) == 1


async def test_an_inactive_price_removes_it_from_the_tiles(
    client: AsyncClient,
) -> None:
    """Retirar un precio saca el plato del selector, que es lo que el dueño espera al retirarlo."""
    from sqlalchemy import select

    from restaurante.modules.menu.infrastructure.models import ProductPriceModel
    from restaurante.shared.database import SessionFactory

    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch(code=f"B{uuid.uuid4().hex[:6]}")
    variant_id = await _create_variant()
    await price_variant_for_branch(variant_id, branch_id, PRICE)
    assert len(await _orderable(client, headers, branch_id)) == 1

    async with SessionFactory() as session:
        row = (
            await session.execute(
                select(ProductPriceModel)
                .where(ProductPriceModel.branch_id == branch_id)
                .execution_options(skip_tenant_filter=True)
            )
        ).scalars().first()
        assert row is not None
        row.is_active = False
        await session.commit()

    assert await _orderable(client, headers, branch_id) == []


# --- El precio del mosaico es el que se cobra ------------------------------
async def test_the_tile_price_is_what_add_item_charges(
    client: AsyncClient,
) -> None:
    """La propiedad que impide que vuelvan a existir dos fórmulas.

    Si el mosaico dijera un número y la línea cobrara otro, el mesero descubriría la diferencia
    cuando el cliente mira la cuenta — que es el peor momento posible.
    """
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch(code=f"B{uuid.uuid4().hex[:6]}")
    employee_id = await _create_employee(
        branch_id, email=f"w{uuid.uuid4().hex[:8]}@demo.com"
    )
    await seed_open_cash_session(branch_id, employee_id)
    variant_id = await _create_variant()
    await price_variant_for_branch(variant_id, branch_id, PRICE)

    tile = (await _orderable(client, headers, branch_id))[0]["variants"][0]

    order_id = (
        await client.post(
            "/orders",
            headers=headers,
            json={
                "branch_id": str(branch_id),
                "channel": "takeaway",
                "employee_id": str(employee_id),
            },
        )
    ).json()["id"]
    line = await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={"product_variant_id": tile["id"], "quantity": 1},
    )

    assert Decimal(line.json()["unit_price"]) == Decimal(tile["price"])


# --- Una petición para todo el catálogo ------------------------------------
async def test_forty_products_come_in_one_request(client: AsyncClient) -> None:
    """El punto entero del endpoint: eran ~81 peticiones y es una."""
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch(code=f"B{uuid.uuid4().hex[:6]}")
    for i in range(40):
        variant_id = await _create_variant(name=f"V{i}")
        await price_variant_for_branch(variant_id, branch_id, PRICE)

    products = await _orderable(client, headers, branch_id)

    assert len(products) == 40
    assert all(len(p["variants"]) == 1 for p in products)
    assert all(Decimal(p["variants"][0]["price"]) == PRICE for p in products)


async def test_reading_the_tiles_needs_menu_read(client: AsyncClient) -> None:
    """`menu.read`, como el resto de lecturas del menú.

    `grant_only` va ANTES de cualquier petición autenticada: los permisos efectivos se cachean con
    TTL, así que una petición previa dejaría cacheados los del admin y el 403 nunca llegaría.
    """
    from tests.modules.messaging.conftest import grant_only

    branch_id = await _create_branch(code=f"B{uuid.uuid4().hex[:6]}")
    await grant_only(["orders.read"])
    headers = await _login(client)

    resp = await client.get(
        "/menu/orderable", headers=headers, params={"branch_id": str(branch_id)}
    )
    assert resp.status_code == 403
