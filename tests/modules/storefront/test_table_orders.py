"""La ingesta del pedido de mesa: se crea Y ENTRA A COCINA cuando el comensal confirma.

Es la excepción deliberada al resto de la carta pública, que deja los pedidos pendientes de que
el personal los confirme. Estos tests la fijan por escrito para que nadie la "arregle" después
por coherencia con el camino web.
"""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select

from restaurante.modules.kitchen.infrastructure.models import (
    KitchenStationModel,
    OrderItemStationModel,
    ProductStationModel,
)
from restaurante.modules.orders.infrastructure.models import (
    DiningTableModel,
    OrderItemModel,
    OrderModel,
)
from restaurante.shared.database import SessionFactory
from tests.modules._cash import seed_open_cash_session
from tests.modules.storefront._seed import (
    SeededMenu,
    demo_tenant_id,
    seed_dining_table,
    seed_menu,
    seed_primary_branch,
)


async def _seed_station_for(seeded: SeededMenu, branch_id: uuid.UUID) -> None:
    """Una estación y el mapeo del producto: sin él, enrutar se niega a dejar el ítem sin ver."""
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        station = KitchenStationModel(
            tenant_id=tenant_id, branch_id=branch_id, name="Plancha", is_active=True
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


def _payload(seeded: SeededMenu, **over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dinerName": "Ana",
        "lines": [
            {
                "variantId": str(seeded.variant_id),
                "quantity": 2,
                "addonIds": [str(seeded.addon_id)],
                "removedIngredients": ["Cebolla"],
                "note": "sin sal",
            }
        ],
    }
    payload.update(over)
    return payload


async def _ticket_count(order_id: uuid.UUID) -> int:
    async with SessionFactory() as session:
        return int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(OrderItemStationModel)
                    .join(
                        OrderItemModel,
                        OrderItemModel.id == OrderItemStationModel.order_item_id,
                    )
                    .where(OrderItemModel.order_id == order_id)
                )
            ).scalar_one()
        )


async def _order(order_id: uuid.UUID) -> OrderModel:
    async with SessionFactory() as session:
        return (
            await session.execute(select(OrderModel).where(OrderModel.id == order_id))
        ).scalar_one()


async def _scenario(*, cash_open: bool = True) -> tuple[SeededMenu, uuid.UUID]:
    branch_id = await seed_primary_branch(code="centro")
    seeded = await seed_menu(branch_id)
    await _seed_station_for(seeded, branch_id)
    if cash_open:
        await seed_open_cash_session(branch_id)
    table_id = await seed_dining_table(branch_id, number="5", code="M5CODE")
    return seeded, table_id


async def test_confirming_creates_the_order_and_fires_it(client: AsyncClient) -> None:
    """El corazón del cambio: confirmar es el compromiso, y el compromiso llega al fogón."""
    seeded, table_id = await _scenario()

    resp = await client.post(
        "/storefront/centro/tables/M5CODE/orders", json=_payload(seeded)
    )

    assert resp.status_code == 201, resp.text
    order_id = uuid.UUID(resp.json()["orderId"])
    order = await _order(order_id)
    assert order.channel == "dine_in"
    assert order.origin == "qr"
    assert order.diner_name == "Ana"
    assert order.dining_table_id == table_id
    assert order.status == "open"
    # Y AQUÍ está la diferencia con el pedido web, que nace sin un solo tiquete.
    assert await _ticket_count(order_id) > 0


async def test_no_phone_and_no_customer_record(client: AsyncClient) -> None:
    """Pedir teléfono para almorzar es fricción que nadie acepta sentado en una mesa."""
    seeded, _ = await _scenario()

    resp = await client.post(
        "/storefront/centro/tables/M5CODE/orders", json=_payload(seeded)
    )

    assert resp.status_code == 201, resp.text
    order = await _order(uuid.UUID(resp.json()["orderId"]))
    assert order.customer_id is None
    assert order.payment_method is None  # se paga al cerrar


async def test_the_diner_gets_their_own_link(client: AsyncClient) -> None:
    seeded, _ = await _scenario()

    resp = await client.post(
        "/storefront/centro/tables/M5CODE/orders", json=_payload(seeded)
    )

    assert resp.json()["editToken"]


async def test_the_order_occupies_its_table(client: AsyncClient) -> None:
    seeded, table_id = await _scenario()

    await client.post("/storefront/centro/tables/M5CODE/orders", json=_payload(seeded))

    async with SessionFactory() as session:
        status = (
            await session.execute(
                select(DiningTableModel.status).where(DiningTableModel.id == table_id)
            )
        ).scalar_one()
    assert status == "occupied"


async def test_each_diner_gets_their_own_order_on_the_same_table(
    client: AsyncClient,
) -> None:
    """Una comanda por persona, todas selladas con la mesa."""
    seeded, table_id = await _scenario()

    ana = await client.post(
        "/storefront/centro/tables/M5CODE/orders", json=_payload(seeded)
    )
    luis = await client.post(
        "/storefront/centro/tables/M5CODE/orders",
        json=_payload(seeded, dinerName="Luis"),
    )

    assert ana.status_code == 201 and luis.status_code == 201
    assert ana.json()["orderId"] != luis.json()["orderId"]
    async with SessionFactory() as session:
        names = sorted(
            (
                await session.execute(
                    select(OrderModel.diner_name).where(
                        OrderModel.dining_table_id == table_id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert names == ["Ana", "Luis"]


async def test_a_second_round_fires_only_what_was_added(client: AsyncClient) -> None:
    """Cada confirmación es una ronda: entra lo nuevo y lo anterior no se duplica."""
    seeded, _ = await _scenario()
    first = await client.post(
        "/storefront/centro/tables/M5CODE/orders", json=_payload(seeded)
    )
    order_id = uuid.UUID(first.json()["orderId"])
    token = first.json()["editToken"]
    before = await _ticket_count(order_id)

    added = await client.patch(
        f"/storefront/orders/{token}",
        json={"add": [{"variantId": str(seeded.variant_id), "quantity": 1}]},
    )

    assert added.status_code == 200, added.text
    after = await _ticket_count(order_id)
    assert after == before * 2  # la ronda nueva, sin reenrutar la anterior


async def test_an_empty_cart_creates_nothing(client: AsyncClient) -> None:
    seeded, _ = await _scenario()

    resp = await client.post(
        "/storefront/centro/tables/M5CODE/orders", json=_payload(seeded, lines=[])
    )

    assert resp.status_code == 422
    async with SessionFactory() as session:
        count = (
            await session.execute(select(func.count()).select_from(OrderModel))
        ).scalar_one()
    assert count == 0


async def test_a_missing_diner_name_is_rejected(client: AsyncClient) -> None:
    seeded, _ = await _scenario()

    resp = await client.post(
        "/storefront/centro/tables/M5CODE/orders", json=_payload(seeded, dinerName="  ")
    )

    assert resp.status_code == 422


async def test_a_closed_caja_creates_nothing(client: AsyncClient) -> None:
    """El portón de verdad sigue siendo la caja, y rechazar no puede dejar medio pedido."""
    seeded, _ = await _scenario(cash_open=False)

    resp = await client.post(
        "/storefront/centro/tables/M5CODE/orders", json=_payload(seeded)
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "cash_closed"
    async with SessionFactory() as session:
        orders = (
            await session.execute(select(func.count()).select_from(OrderModel))
        ).scalar_one()
        tickets = (
            await session.execute(
                select(func.count()).select_from(OrderItemStationModel)
            )
        ).scalar_one()
    assert orders == 0
    assert tickets == 0


async def test_an_unknown_variant_creates_nothing(client: AsyncClient) -> None:
    seeded, _ = await _scenario()

    resp = await client.post(
        "/storefront/centro/tables/M5CODE/orders",
        json=_payload(
            seeded,
            lines=[{"variantId": str(uuid.uuid4()), "quantity": 1}],
        ),
    )

    assert resp.status_code == 422
    async with SessionFactory() as session:
        count = (
            await session.execute(select(func.count()).select_from(OrderModel))
        ).scalar_one()
    assert count == 0


async def test_the_payment_gate_lets_a_methodless_order_cook(
    client: AsyncClient,
) -> None:
    """Fija por escrito el hecho que sostiene todo el diseño.

    `may_cook` hace `(payment_method or CASH) == CASH`, así que un pedido de mesa —que no elige
    método porque se paga al cerrar— cuenta como efectivo y pasa. Si algún día alguien endurece
    esa regla sin mirar, este test es lo que se lo dice: sin él, el síntoma sería una mesa que
    pide y una cocina que nunca se entera.
    """
    seeded, _ = await _scenario()

    resp = await client.post(
        "/storefront/centro/tables/M5CODE/orders", json=_payload(seeded)
    )

    order_id = uuid.UUID(resp.json()["orderId"])
    assert (await _order(order_id)).payment_method is None
    assert await _ticket_count(order_id) > 0
