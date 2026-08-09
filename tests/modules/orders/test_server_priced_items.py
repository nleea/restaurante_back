"""El servidor pone el precio de una línea, y el cliente no puede cambiarlo.

Cuatro propiedades, y las cuatro son del camino del dinero:

1. **Un `unit_price` en el cuerpo no afecta a lo que se cobra.** Es la que demuestra que la puerta
   está cerrada, no sólo que ya nadie la usa. El campo se sigue aceptando durante una versión para
   poder desplegar el backend antes que el frontend.
2. **Sin precio en la sede se rechaza y no se crea nada.** Antes se vendía a cero.
3. **El precio se ESTAMPA.** Cambiar el precio del catálogo después no mueve una línea ya vendida
   ni el total de su comanda: una cuenta de ayer conserva los números de ayer.
4. **Una línea nueva tras el cambio lleva el precio nuevo**, junto a las viejas con el viejo.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.menu.infrastructure.models import ProductPriceModel
from restaurante.shared.database import SessionFactory
from tests.modules._cash import seed_open_cash_session
from tests.modules._menu import price_variant_for_branch
from tests.modules.orders.test_orders_api import (
    _assign_role,
    _create_branch,
    _create_employee,
    _create_variant,
    _login,
)

BASE = Decimal("10000.00")


async def _order_on_branch(
    client: AsyncClient, headers: dict[str, str], branch_id: uuid.UUID
) -> str:
    employee_id = await _create_employee(
        branch_id, email=f"w{uuid.uuid4().hex[:8]}@demo.com"
    )
    await seed_open_cash_session(branch_id, employee_id)
    resp = await client.post(
        "/orders",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "channel": "takeaway",
            "employee_id": str(employee_id),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _scenario(
    client: AsyncClient, *, price: Decimal | None = BASE
) -> tuple[dict[str, str], str, uuid.UUID, uuid.UUID]:
    """Sede + comanda abierta + variante vendible. `price=None` la deja SIN precio."""
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch(code=f"B{uuid.uuid4().hex[:6]}")
    order_id = await _order_on_branch(client, headers, branch_id)
    variant_id = await _create_variant(name=f"V{uuid.uuid4().hex[:6]}")
    if price is not None:
        await price_variant_for_branch(variant_id, branch_id, price)
    return headers, order_id, variant_id, branch_id


async def _add(
    client: AsyncClient,
    headers: dict[str, str],
    order_id: str,
    variant_id: uuid.UUID,
    quantity: int = 1,
    **extra: object,
) -> object:
    return await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={
            "product_variant_id": str(variant_id),
            "quantity": quantity,
            **extra,
        },
    )


async def _reprice(
    variant_id: uuid.UUID, branch_id: uuid.UUID, price: Decimal
) -> None:
    """Cambia el precio del CATÁLOGO, como lo haría el dueño desde /menu."""
    async with SessionFactory() as session:
        row = (
            await session.execute(
                select(ProductPriceModel)
                .where(ProductPriceModel.branch_id == branch_id)
                .execution_options(skip_tenant_filter=True)
            )
        ).scalars().first()
        assert row is not None
        row.price = price
        await session.commit()


# --- La puerta está cerrada -------------------------------------------------
async def test_the_server_prices_the_line(client: AsyncClient) -> None:
    headers, order_id, variant_id, _ = await _scenario(client)

    resp = await _add(client, headers, order_id, variant_id, quantity=2)

    assert resp.status_code == 201, resp.text
    assert Decimal(resp.json()["unit_price"]) == BASE
    assert Decimal(resp.json()["line_subtotal"]) == BASE * 2


async def test_a_unit_price_in_the_body_changes_nothing(client: AsyncClient) -> None:
    """La prueba que demuestra que la puerta está CERRADA, no sólo que nadie la usa.

    El campo se sigue aceptando durante una versión —es lo que permite desplegar este backend antes
    del frontend— así que "ya nadie lo manda" no es una garantía: hay que afirmar que da igual.
    """
    headers, order_id, variant_id, _ = await _scenario(client)

    resp = await _add(
        client, headers, order_id, variant_id, unit_price="1", quantity=1
    )

    assert resp.status_code == 201, resp.text
    assert Decimal(resp.json()["unit_price"]) == BASE


async def test_an_absurd_unit_price_changes_nothing(client: AsyncClient) -> None:
    """Un número enorme tampoco pasa. Antes de esto, esta petición cobraba un millón."""
    headers, order_id, variant_id, _ = await _scenario(client)

    resp = await _add(
        client, headers, order_id, variant_id, unit_price="1000000.00"
    )

    assert Decimal(resp.json()["unit_price"]) == BASE


# --- Sin precio: se rechaza, no se regala ----------------------------------
async def test_a_product_without_a_branch_price_is_refused(
    client: AsyncClient,
) -> None:
    headers, order_id, variant_id, _ = await _scenario(client, price=None)

    resp = await _add(client, headers, order_id, variant_id)

    assert resp.status_code == 422, resp.text
    assert "precio" in resp.text.lower()


async def test_the_refusal_creates_nothing(client: AsyncClient) -> None:
    """Ni a cero ni a medias: la comanda se queda sin líneas y con total cero."""
    headers, order_id, variant_id, _ = await _scenario(client, price=None)

    await _add(client, headers, order_id, variant_id)

    items = await client.get(f"/orders/{order_id}/items", headers=headers)
    assert items.json() == []
    order = await client.get(f"/orders/{order_id}", headers=headers)
    assert Decimal(order.json()["total"]) == Decimal("0")


async def test_a_price_in_another_branch_does_not_rescue_the_sale(
    client: AsyncClient,
) -> None:
    """El producto está preciado, pero no aquí. Es el caso que un `WHERE` flojo dejaría pasar."""
    await _assign_role("admin")
    headers = await _login(client)
    priced = await _create_branch(code=f"A{uuid.uuid4().hex[:6]}")
    selling = await _create_branch(code=f"B{uuid.uuid4().hex[:6]}")
    variant_id = await _create_variant(name=f"V{uuid.uuid4().hex[:6]}")
    await price_variant_for_branch(variant_id, priced, BASE)
    order_id = await _order_on_branch(client, headers, selling)

    resp = await _add(client, headers, order_id, variant_id)

    assert resp.status_code == 422


# --- El precio se estampa --------------------------------------------------
async def test_a_later_price_change_does_not_move_a_sold_line(
    client: AsyncClient,
) -> None:
    """Una cuenta de ayer conserva los números de ayer. Es lo que hace correcta una caja cerrada."""
    headers, order_id, variant_id, branch_id = await _scenario(client)
    item = (await _add(client, headers, order_id, variant_id, quantity=2)).json()

    await _reprice(variant_id, branch_id, Decimal("99000.00"))

    items = (await client.get(f"/orders/{order_id}/items", headers=headers)).json()
    assert Decimal(items[0]["unit_price"]) == BASE
    assert Decimal(items[0]["line_subtotal"]) == BASE * 2
    order = (await client.get(f"/orders/{order_id}", headers=headers)).json()
    assert Decimal(order["total"]) == BASE * 2
    assert items[0]["id"] == item["id"]


async def test_a_new_line_after_the_change_carries_the_new_price(
    client: AsyncClient,
) -> None:
    """Las dos conviven: la vieja con el precio viejo y la nueva con el nuevo."""
    headers, order_id, variant_id, branch_id = await _scenario(client)
    await _add(client, headers, order_id, variant_id)

    await _reprice(variant_id, branch_id, Decimal("12000.00"))
    await _add(client, headers, order_id, variant_id)

    items = (await client.get(f"/orders/{order_id}/items", headers=headers)).json()
    prices = sorted(Decimal(i["unit_price"]) for i in items)
    assert prices == [BASE, Decimal("12000.00")]
    order = (await client.get(f"/orders/{order_id}", headers=headers)).json()
    assert Decimal(order["total"]) == BASE + Decimal("12000.00")


async def test_deactivating_the_price_stops_new_sales_but_keeps_the_old_line(
    client: AsyncClient,
) -> None:
    """Retirar un precio no reescribe lo vendido; sólo impide vender más."""
    headers, order_id, variant_id, branch_id = await _scenario(client)
    await _add(client, headers, order_id, variant_id)

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

    refused = await _add(client, headers, order_id, variant_id)
    assert refused.status_code == 422

    items = (await client.get(f"/orders/{order_id}/items", headers=headers)).json()
    assert len(items) == 1
    assert Decimal(items[0]["unit_price"]) == BASE
