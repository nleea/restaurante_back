"""Las reglas de «mi pedido», ejercidas por HTTP: las dos ventanas, el pago y la invariante.

Las funciones puras ya están probadas sin base de datos (`test_order_edit_rules.py`). Lo que
se prueba aquí es lo otro: que el endpoint las aplique **releyendo la base**, y no lo que el
cliente traiga ni lo que la vista leyera hace veinte minutos.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select, update

from restaurante.modules.delivery.infrastructure.models import OrderDeliveryModel
from restaurante.modules.kitchen.infrastructure.models import (
    KitchenStationModel,
    OrderItemStationModel,
    ProductStationModel,
)
from restaurante.modules.orders.infrastructure.models import (
    OrderItemModel,
    OrderModel,
    OrderPaymentModel,
)
from restaurante.shared.database import SessionFactory
from tests.modules._cash import seed_open_cash_session
from tests.modules.storefront._seed import (
    SeededMenu,
    demo_tenant_id,
    seed_delivery_ready,
    seed_extra_variant,
    seed_menu,
    seed_primary_branch,
)

PRICE = "28000.00"


def _payload(seeded: SeededMenu, kind: str, lines: int = 1) -> dict[str, Any]:
    fulfillment: dict[str, Any] = (
        {"type": "delivery", "addressText": "Calle 1 #2-3"}
        if kind == "delivery"
        else {"type": "pickup"}
    )
    return {
        "customer": {"name": "Ana Pérez", "phone": "3001234567"},
        "fulfillment": fulfillment,
        "paymentMethod": "efectivo",
        "lines": [
            {"variantId": str(seeded.variant_id), "quantity": 1} for _ in range(lines)
        ],
    }


async def _open(
    client: AsyncClient, kind: str = "pickup", lines: int = 1
) -> tuple[SeededMenu, str]:
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id, price=PRICE)
    await seed_open_cash_session(branch_id)
    # La carta no acepta un domicilio de una sede que no puede cotizarlo, así que una sede que
    # va a recibir uno tiene que tener pin y tarifa — como en producción.
    await seed_delivery_ready(branch_id)
    resp = await client.post("/storefront/orders", json=_payload(seeded, kind, lines))
    assert resp.status_code == 201, resp.text
    return seeded, str(resp.json()["editToken"])


async def _set_kitchen_state(token: str, state: str) -> None:
    async with SessionFactory() as session:
        await session.execute(
            update(OrderModel)
            .where(OrderModel.edit_token == token)
            .values(kitchen_state=state)
        )
        await session.commit()


async def _set_delivery_status(token: str, status: str) -> None:
    async with SessionFactory() as session:
        order_id = (
            await session.execute(
                select(OrderModel.id).where(OrderModel.edit_token == token)
            )
        ).scalar_one()
        await session.execute(
            update(OrderDeliveryModel)
            .where(OrderDeliveryModel.order_id == order_id)
            .values(delivery_status=status)
        )
        await session.commit()


async def _pay_in_full(token: str) -> None:
    """Un pago que cubre el total. Pagar NO cierra la comanda: el pedido sigue abierto."""
    async with SessionFactory() as session:
        order = (
            await session.execute(
                select(OrderModel).where(OrderModel.edit_token == token)
            )
        ).scalar_one()
        session.add(
            OrderPaymentModel(
                tenant_id=order.tenant_id,
                branch_id=order.branch_id,
                order_id=order.id,
                cash_session_id=order.cash_session_id,
                amount=Decimal(order.total),
                method="efectivo",
                employee_id=order.employee_id,
            )
        )
        await session.commit()


async def _map_product_to_a_station(seeded: SeededMenu) -> None:
    """Sin este mapeo, enrutar no crea ticket alguno y "llegó a cocina" no se puede afirmar."""
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        station = KitchenStationModel(
            tenant_id=tenant_id, branch_id=seeded.branch_id, name="Plancha"
        )
        session.add(station)
        await session.flush()
        session.add(
            ProductStationModel(
                tenant_id=tenant_id,
                product_id=seeded.product_id,
                kitchen_station_id=station.id,
                tasks=[],
            )
        )
        await session.commit()


async def _start_cooking(seeded: SeededMenu, item_id: str) -> None:
    """Una estación de ESE ítem ya en marcha. `item_id` llega como texto desde la vista."""
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        station = KitchenStationModel(
            tenant_id=tenant_id, branch_id=seeded.branch_id, name="Plancha"
        )
        session.add(station)
        await session.flush()
        session.add(
            OrderItemStationModel(
                tenant_id=tenant_id,
                branch_id=seeded.branch_id,
                order_item_id=uuid.UUID(item_id),
                kitchen_station_id=station.id,
                status="in_progress",
                tasks=[],
            )
        )
        await session.commit()


# --- La invariante del total -------------------------------------------------
async def test_swapping_a_product_passes_at_the_same_price_and_up_but_not_down(
    client: AsyncClient,
) -> None:
    seeded, token = await _open(client)
    same = await seed_extra_variant(seeded, name="Ceviche de Camarón", price=PRICE)
    cheaper = await seed_extra_variant(seeded, name="Limonada", price="5000.00")
    dearer = await seed_extra_variant(seeded, name="Langostinos", price="45000.00")
    item_id = (await client.get(f"/storefront/orders/{token}")).json()["lines"][0][
        "itemId"
    ]

    # Mismo precio: pasa. Y de paso demuestra que el intermedio del cambio —quitar, que baja
    # el total— no dispara nada: lo que se juzga es el RESULTADO.
    resp = await client.patch(
        f"/storefront/orders/{token}",
        json={"edit": [{"itemId": item_id, "variantId": str(same)}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["order"]["total"] == PRICE

    to_cheaper = await client.patch(
        f"/storefront/orders/{token}",
        json={"edit": [{"itemId": item_id, "variantId": str(cheaper)}]},
    )
    assert to_cheaper.status_code == 409
    assert to_cheaper.json()["refusal"] == "total_would_drop"

    to_dearer = await client.patch(
        f"/storefront/orders/{token}",
        json={"edit": [{"itemId": item_id, "variantId": str(dearer)}]},
    )
    assert to_dearer.status_code == 200, to_dearer.text
    assert to_dearer.json()["order"]["total"] == "45000.00"


# --- Ventana por ítem --------------------------------------------------------
async def test_one_started_item_does_not_freeze_the_other(client: AsyncClient) -> None:
    seeded, token = await _open(client, lines=2)
    view = (await client.get(f"/storefront/orders/{token}")).json()
    cooking, untouched = view["lines"][0], view["lines"][1]
    await _start_cooking(seeded, cooking["itemId"])

    after = (await client.get(f"/storefront/orders/{token}")).json()
    by_id = {line["itemId"]: line for line in after["lines"]}
    assert by_id[cooking["itemId"]]["editable"] is False
    assert by_id[untouched["itemId"]]["editable"] is True

    resp = await client.patch(
        f"/storefront/orders/{token}",
        json={"edit": [{"itemId": untouched["itemId"], "quantity": 2}]},
    )
    assert resp.status_code == 200, resp.text


async def test_the_kitchen_starting_between_painting_and_confirming_wins(
    client: AsyncClient,
) -> None:
    """La vista dijo que sí; la plancha empezó después. Manda la base al escribir."""
    seeded, token = await _open(client)
    painted = (await client.get(f"/storefront/orders/{token}")).json()
    assert painted["lines"][0]["editable"] is True

    await _start_cooking(seeded, painted["lines"][0]["itemId"])

    resp = await client.patch(
        f"/storefront/orders/{token}",
        json={"edit": [{"itemId": painted["lines"][0]["itemId"], "quantity": 2}]},
    )
    assert resp.status_code == 409
    assert resp.json()["refusal"] == "item_started"


# --- Ventana por pedido ------------------------------------------------------
async def test_a_delivery_in_transit_closes_the_whole_view(client: AsyncClient) -> None:
    seeded, token = await _open(client, kind="delivery")
    await _set_delivery_status(token, "in_transit")

    view = (await client.get(f"/storefront/orders/{token}")).json()
    assert view["editable"] is False
    assert view["refusal"] == "out_of_reach"

    resp = await client.patch(
        f"/storefront/orders/{token}",
        json={"add": [{"variantId": str(seeded.variant_id), "quantity": 1}]},
    )
    assert resp.status_code == 409
    assert resp.json()["refusal"] == "out_of_reach"


async def test_a_ready_delivery_still_at_the_pass_accepts_one_more_thing(
    client: AsyncClient,
) -> None:
    """Entre `ready` y `in_transit` la bolsa sigue en el pase: el cocinero puede hacer una más."""
    seeded, token = await _open(client, kind="delivery")
    await _map_product_to_a_station(seeded)
    await _set_kitchen_state(token, "ready")
    await _set_delivery_status(token, "pending")

    view = (await client.get(f"/storefront/orders/{token}")).json()
    assert view["editable"] is True

    resp = await client.patch(
        f"/storefront/orders/{token}",
        json={"add": [{"variantId": str(seeded.variant_id), "quantity": 1}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["order"]["total"] == "56000.00"

    # Y llega a la cocina: el pedido ya estaba enrutado, así que lo añadido no puede quedarse
    # esperando a que alguien lo mande. El domiciliario espera dos minutos; la cuenta no.
    async with SessionFactory() as session:
        routed = set(
            (
                await session.execute(select(OrderItemStationModel.order_item_id))
            ).scalars()
        )
        items = set((await session.execute(select(OrderItemModel.id))).scalars())
    assert routed == items


async def test_a_pickup_order_closes_at_ready(client: AsyncClient) -> None:
    """Sin entrega no hay "salir": la comida espera en el mostrador y el cliente puede llegar."""
    seeded, token = await _open(client)
    await _set_kitchen_state(token, "ready")

    view = (await client.get(f"/storefront/orders/{token}")).json()
    assert view["editable"] is False
    assert view["refusal"] == "out_of_reach"

    resp = await client.patch(
        f"/storefront/orders/{token}",
        json={"add": [{"variantId": str(seeded.variant_id), "quantity": 1}]},
    )
    assert resp.status_code == 409


# --- Con pago ----------------------------------------------------------------
async def test_a_paid_order_grows_but_its_lines_keep_their_identity(
    client: AsyncClient,
) -> None:
    seeded, token = await _open(client)
    other = await seed_extra_variant(seeded, name="Langostinos", price="45000.00")
    await _pay_in_full(token)
    item_id = (await client.get(f"/storefront/orders/{token}")).json()["lines"][0][
        "itemId"
    ]

    # El cambio de producto se prueba PRIMERO y a propósito: crecer descubre el total y el
    # pedido deja de estar saldado, con lo que la regla de la línea congelada ya no aplicaría.
    swap = await client.patch(
        f"/storefront/orders/{token}",
        json={"edit": [{"itemId": item_id, "variantId": str(other)}]},
    )
    assert swap.status_code == 409
    assert swap.json()["refusal"] == "paid_line"

    grow = await client.patch(
        f"/storefront/orders/{token}",
        json={
            "edit": [
                {
                    "itemId": item_id,
                    "quantity": 2,
                    "addAddonIds": [str(seeded.addon_id)],
                }
            ]
        },
    )
    assert grow.status_code == 200, grow.text

    added = await client.patch(
        f"/storefront/orders/{token}",
        json={"add": [{"variantId": str(other), "quantity": 1}]},
    )
    assert added.status_code == 200, added.text
    body = added.json()["order"]
    # Lo pagado queda congelado y lo nuevo se ve aparte: línea nueva, no la vieja crecida.
    assert len(body["lines"]) == 2
    assert body["lines"][0]["itemId"] == item_id
    assert body["outstanding"] != "0.00"


async def test_a_refused_edit_leaves_the_order_exactly_as_it_was(
    client: AsyncClient,
) -> None:
    seeded, token = await _open(client)
    cheaper = await seed_extra_variant(seeded, name="Limonada", price="5000.00")
    before = (await client.get(f"/storefront/orders/{token}")).json()
    item_id = before["lines"][0]["itemId"]

    async with SessionFactory() as session:
        rows_before = [
            (i.id, i.product_variant_id, i.quantity, i.unit_price, i.notes)
            for i in (
                await session.execute(select(OrderItemModel).order_by(OrderItemModel.id))
            ).scalars()
        ]

    # Dos gestos en una sola edición: una nota que sí se podría escribir y un cambio de
    # producto que no. Si se escribiera antes de juzgar, la nota quedaría puesta.
    refused = await client.patch(
        f"/storefront/orders/{token}",
        json={
            "edit": [
                {
                    "itemId": item_id,
                    "removedIngredients": [seeded.removable_name],
                    "variantId": str(cheaper),
                }
            ]
        },
    )
    assert refused.status_code == 409
    assert refused.json()["refusal"] == "total_would_drop"

    async with SessionFactory() as session:
        rows_after = [
            (i.id, i.product_variant_id, i.quantity, i.unit_price, i.notes)
            for i in (
                await session.execute(select(OrderItemModel).order_by(OrderItemModel.id))
            ).scalars()
        ]
    assert rows_after == rows_before
    assert (await client.get(f"/storefront/orders/{token}")).json() == before
