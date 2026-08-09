"""Una línea se lee sola, y una lista de comandas trae sus líneas en una petición.

Las dos mitades que matan el fan-out del navegador. Antes, para pintar una comanda, el cliente se
bajaba el menú entero (una petición por producto) sólo para traducir `product_variant_id` en
"Bandeja paisa · Grande"; y para pintar un salón, una petición por mesa.

La propiedad que más importa y la que menos se ve: **renombrar un producto cambia lo que dice una
comanda viva y NO cambia su precio.** Es la diferencia entre los dos campos nuevos y el que ya
había: el precio se estampa porque es dinero, el nombre se resuelve porque es una etiqueta.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.menu.infrastructure.models import (
    ProductModel,
    ProductVariantModel,
)
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

PRICE = Decimal("10000.00")


async def _rename_product(variant_id: uuid.UUID, name: str) -> None:
    """Renombra el producto de esa variante, como lo haría el dueño desde /menu."""
    async with SessionFactory() as session:
        product_id = (
            await session.execute(
                select(ProductVariantModel.product_id)
                .where(ProductVariantModel.id == variant_id)
                .execution_options(skip_tenant_filter=True)
            )
        ).scalar_one()
        product = (
            await session.execute(
                select(ProductModel)
                .where(ProductModel.id == product_id)
                .execution_options(skip_tenant_filter=True)
            )
        ).scalar_one()
        product.name = name
        await session.commit()


async def _branch_with_order(
    client: AsyncClient, headers: dict[str, str]
) -> tuple[uuid.UUID, str, uuid.UUID]:
    branch_id = await _create_branch(code=f"B{uuid.uuid4().hex[:6]}")
    employee_id = await _create_employee(
        branch_id, email=f"w{uuid.uuid4().hex[:8]}@demo.com"
    )
    await seed_open_cash_session(branch_id, employee_id)
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
    return branch_id, order_id, employee_id


# --- La línea se lee sola ---------------------------------------------------
async def test_a_line_reads_with_its_product_and_variant_names(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id, order_id, _ = await _branch_with_order(client, headers)
    variant_id = await _create_variant(name="Grande")
    await price_variant_for_branch(variant_id, branch_id, PRICE)
    await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={"product_variant_id": str(variant_id), "quantity": 1},
    )

    items = (await client.get(f"/orders/{order_id}/items", headers=headers)).json()

    assert items[0]["product_name"] == "Classic Burger"
    assert items[0]["variant_name"] == "Grande"


async def test_the_create_response_already_carries_the_labels(
    client: AsyncClient,
) -> None:
    """El POST también las trae: un campo que a veces viene nulo sin motivo es una trampa."""
    await _assign_role("admin")
    headers = await _login(client)
    branch_id, order_id, _ = await _branch_with_order(client, headers)
    variant_id = await _create_variant(name="Mediana")
    await price_variant_for_branch(variant_id, branch_id, PRICE)

    created = await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={"product_variant_id": str(variant_id), "quantity": 1},
    )

    assert created.json()["product_name"] == "Classic Burger"
    assert created.json()["variant_name"] == "Mediana"


async def test_renaming_the_product_changes_the_line_but_not_its_price(
    client: AsyncClient,
) -> None:
    """La prueba que separa los dos campos nuevos del que ya existía.

    El nombre se resuelve al leer, así que sigue al catálogo. El precio se estampó al vender, así
    que no se mueve. Si el nombre se guardara en la fila, esta prueba fallaría — y una comanda viva
    seguiría diciendo el nombre viejo.
    """
    await _assign_role("admin")
    headers = await _login(client)
    branch_id, order_id, _ = await _branch_with_order(client, headers)
    variant_id = await _create_variant(name="Grande")
    await price_variant_for_branch(variant_id, branch_id, PRICE)
    await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={"product_variant_id": str(variant_id), "quantity": 1},
    )

    await _rename_product(variant_id, "Hamburguesa de la casa")

    items = (await client.get(f"/orders/{order_id}/items", headers=headers)).json()
    assert items[0]["product_name"] == "Hamburguesa de la casa"
    assert Decimal(items[0]["unit_price"]) == PRICE


# --- La lista trae sus líneas -----------------------------------------------
async def test_including_items_brings_them_with_their_labels(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id, order_id, _ = await _branch_with_order(client, headers)
    variant_id = await _create_variant(name="Grande")
    await price_variant_for_branch(variant_id, branch_id, PRICE)
    await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={"product_variant_id": str(variant_id), "quantity": 2},
    )

    listed = await client.get(
        "/orders",
        headers=headers,
        params={"branch_id": str(branch_id), "include": "items"},
    )

    assert listed.status_code == 200, listed.text
    order = next(o for o in listed.json() if o["id"] == order_id)
    assert len(order["items"]) == 1
    assert order["items"][0]["product_name"] == "Classic Burger"
    assert Decimal(order["items"][0]["unit_price"]) == PRICE


async def test_not_asking_costs_nothing_and_changes_no_field(
    client: AsyncClient,
) -> None:
    """Sin `include` la respuesta trae todos los campos de siempre y `items` en nulo.

    Es la propiedad que hace que esto sea aditivo: quien no lo pide no paga y no ve nada distinto en
    los campos que ya usaba.
    """
    await _assign_role("admin")
    headers = await _login(client)
    branch_id, order_id, _ = await _branch_with_order(client, headers)
    variant_id = await _create_variant()
    await price_variant_for_branch(variant_id, branch_id, PRICE)
    await client.post(
        f"/orders/{order_id}/items",
        headers=headers,
        json={"product_variant_id": str(variant_id), "quantity": 1},
    )

    plain = (
        await client.get(
            "/orders", headers=headers, params={"branch_id": str(branch_id)}
        )
    ).json()[0]
    included = (
        await client.get(
            "/orders",
            headers=headers,
            params={"branch_id": str(branch_id), "include": "items"},
        )
    ).json()[0]

    assert plain["items"] is None
    # Todo lo demás, idéntico.
    assert {k: v for k, v in plain.items() if k != "items"} == {
        k: v for k, v in included.items() if k != "items"
    }


async def test_an_unknown_include_is_ignored(client: AsyncClient) -> None:
    """Una clave desconocida no trae nada y no revienta: es UNA clave admitida, no una lista."""
    await _assign_role("admin")
    headers = await _login(client)
    branch_id, order_id, _ = await _branch_with_order(client, headers)

    listed = await client.get(
        "/orders",
        headers=headers,
        params={"branch_id": str(branch_id), "include": "payments"},
    )

    assert listed.status_code == 200
    assert listed.json()[0]["items"] is None


async def test_many_orders_need_one_request(client: AsyncClient) -> None:
    """Doce comandas, una petición. Era una por comanda, y es la mitad del fan-out que se mata."""
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch(code=f"B{uuid.uuid4().hex[:6]}")
    employee_id = await _create_employee(
        branch_id, email=f"w{uuid.uuid4().hex[:8]}@demo.com"
    )
    await seed_open_cash_session(branch_id, employee_id)
    variant_id = await _create_variant()
    await price_variant_for_branch(variant_id, branch_id, PRICE)

    for _ in range(12):
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
        await client.post(
            f"/orders/{order_id}/items",
            headers=headers,
            json={"product_variant_id": str(variant_id), "quantity": 1},
        )

    listed = (
        await client.get(
            "/orders",
            headers=headers,
            params={"branch_id": str(branch_id), "include": "items"},
        )
    ).json()

    assert len(listed) == 12
    assert all(len(o["items"]) == 1 for o in listed)
    assert all(o["items"][0]["product_name"] == "Classic Burger" for o in listed)
