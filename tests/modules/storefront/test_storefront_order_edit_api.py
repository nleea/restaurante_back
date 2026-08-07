"""«Mi pedido»: la superficie pública que abre y corrige un pedido por su token.

Todo pasa por HTTP y por el token que devolvió la creación del pedido — que es exactamente lo
que tiene el cliente y nada más. Sin login, sin cabeceras, sin conocer el id del pedido.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from restaurante.main import app
from restaurante.modules.kitchen.infrastructure.models import (
    KitchenStationModel,
    OrderItemStationModel,
    ProductStationModel,
)
from restaurante.modules.orders.infrastructure.models import OrderItemModel, OrderModel
from restaurante.shared.api.prefix import API_PREFIX
from restaurante.shared.audit.models import AuditLogModel
from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import TenantModel
from tests.modules._cash import seed_open_cash_session
from tests.modules.storefront._seed import (
    SeededMenu,
    demo_tenant_id,
    seed_menu,
    seed_primary_branch,
)

PRICE = "28000.00"


async def _order_with_token(client: AsyncClient, seeded: SeededMenu) -> str:
    """Un pedido de la carta y el token con el que su dueño vuelve a abrirlo."""
    payload: dict[str, Any] = {
        "customer": {"name": "Ana Pérez", "phone": "3001234567"},
        "fulfillment": {"type": "pickup"},
        "paymentMethod": "efectivo",
        "lines": [
            {
                "variantId": str(seeded.variant_id),
                "quantity": 1,
                "removedIngredients": [seeded.removable_name],
                "note": "tocar timbre",
            }
        ],
    }
    resp = await client.post("/storefront/orders", json=payload)
    assert resp.status_code == 201, resp.text
    token = resp.json()["editToken"]
    assert token
    return str(token)


async def _seed_all(client: AsyncClient) -> tuple[SeededMenu, str]:
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id, price=PRICE)
    await seed_open_cash_session(branch_id)
    return seeded, await _order_with_token(client, seeded)


async def test_the_token_opens_its_order_with_lines_totals_and_editability(
    client: AsyncClient,
) -> None:
    seeded, token = await _seed_all(client)

    resp = await client.get(f"/storefront/orders/{token}")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["status"] == "open"
    assert body["total"] == PRICE
    assert body["paid"] == "0.00"
    assert body["outstanding"] == PRICE
    assert body["editable"] is True
    assert body["refusal"] is None

    (line,) = body["lines"]
    assert line["name"] == "Ceviche Mixto"
    assert line["quantity"] == 1
    assert line["unitPrice"] == PRICE
    assert line["editable"] is True
    # La nota se devuelve DESCOMPUESTA: la exclusión como casilla marcada y el texto libre
    # aparte, que es lo que evita que corregir una cosa se lleve por delante la otra.
    assert line["removedIngredients"] == [seeded.removable_name]
    assert line["note"] == "tocar timbre"
    assert seeded.removable_name in line["removableIngredients"]
    assert seeded.staple_name not in line["removableIngredients"]


async def test_unknown_and_expired_tokens_answer_the_same(client: AsyncClient) -> None:
    _, token = await _seed_all(client)

    unknown = await client.get(f"/storefront/orders/{'z' * 43}")
    assert unknown.status_code == 404

    async with SessionFactory() as session:
        await session.execute(
            update(OrderModel)
            .where(OrderModel.edit_token == token)
            .values(edit_token_expires_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await session.commit()

    expired = await client.get(f"/storefront/orders/{token}")
    assert expired.status_code == 404
    # Indistinguibles: si el cuerpo delatara cuál existió, probar enlaces diría qué pedidos hay.
    assert expired.json() == unknown.json()


async def test_adding_a_line_ignores_a_client_supplied_price(
    client: AsyncClient,
) -> None:
    seeded, token = await _seed_all(client)

    resp = await client.patch(
        f"/storefront/orders/{token}",
        json={
            "add": [
                {
                    "variantId": str(seeded.variant_id),
                    "quantity": 1,
                    "addonIds": [str(seeded.addon_id)],
                    # Un precio enviado por el cliente. No hay campo para él: se ignora.
                    "unitPrice": "1.00",
                }
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["totalBefore"] == PRICE
    # 28000 (lo que ya había) + 28000 (la línea nueva) + 6000 (la adición), al precio del
    # catálogo y no al que mandó el cliente.
    assert body["order"]["total"] == "62000.00"
    assert body["order"]["outstanding"] == "62000.00"
    assert len(body["order"]["lines"]) == 2


async def test_lowering_a_quantity_is_refused_and_leaves_the_order_untouched(
    client: AsyncClient,
) -> None:
    seeded, token = await _seed_all(client)
    view = (await client.get(f"/storefront/orders/{token}")).json()
    item_id = view["lines"][0]["itemId"]

    bump = await client.patch(
        f"/storefront/orders/{token}",
        json={"edit": [{"itemId": item_id, "quantity": 3}]},
    )
    assert bump.status_code == 200, bump.text
    assert bump.json()["order"]["total"] == "84000.00"

    drop = await client.patch(
        f"/storefront/orders/{token}",
        json={"edit": [{"itemId": item_id, "quantity": 1}]},
    )
    assert drop.status_code == 409
    assert drop.json()["refusal"] == "total_would_drop"
    assert drop.json()["code"] == "order_edit_refused"

    after = (await client.get(f"/storefront/orders/{token}")).json()
    assert after["total"] == "84000.00"
    assert after["lines"][0]["quantity"] == 3


async def test_a_started_item_is_read_only_and_says_why(client: AsyncClient) -> None:
    seeded, token = await _seed_all(client)
    tenant_id = await demo_tenant_id()

    async with SessionFactory() as session:
        item = (
            await session.execute(
                select(OrderItemModel).where(
                    OrderItemModel.product_variant_id == seeded.variant_id
                )
            )
        ).scalar_one()
        station = KitchenStationModel(
            tenant_id=tenant_id, branch_id=seeded.branch_id, name="Plancha"
        )
        session.add(station)
        await session.flush()
        session.add(
            OrderItemStationModel(
                tenant_id=tenant_id,
                branch_id=seeded.branch_id,
                order_item_id=item.id,
                kitchen_station_id=station.id,
                status="in_progress",
                tasks=[],
            )
        )
        await session.commit()
        item_id = item.id

    view = (await client.get(f"/storefront/orders/{token}")).json()
    # El pedido sigue abierto: lo que se apaga es ESA línea, no la pantalla entera.
    assert view["editable"] is True
    (line,) = view["lines"]
    assert line["editable"] is False
    assert line["refusal"] == "item_started"
    assert line["reason"]

    refused = await client.patch(
        f"/storefront/orders/{token}",
        json={"edit": [{"itemId": str(item_id), "quantity": 5}]},
    )
    assert refused.status_code == 409
    assert refused.json()["refusal"] == "item_started"


async def test_adding_is_still_allowed_while_another_item_cooks(
    client: AsyncClient,
) -> None:
    """La limonada empezada no puede impedir pedir otra cosa: la ventana es por ítem."""
    seeded, token = await _seed_all(client)
    tenant_id = await demo_tenant_id()

    async with SessionFactory() as session:
        item = (
            await session.execute(select(OrderItemModel).limit(1))
        ).scalar_one()
        station = KitchenStationModel(
            tenant_id=tenant_id, branch_id=seeded.branch_id, name="Plancha"
        )
        session.add(station)
        await session.flush()
        session.add(
            OrderItemStationModel(
                tenant_id=tenant_id,
                branch_id=seeded.branch_id,
                order_item_id=item.id,
                kitchen_station_id=station.id,
                status="in_progress",
                tasks=[],
            )
        )
        await session.commit()

    resp = await client.patch(
        f"/storefront/orders/{token}",
        json={"add": [{"variantId": str(seeded.variant_id), "quantity": 1}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["order"]["total"] == "56000.00"


async def test_what_is_added_to_an_order_already_cooking_reaches_the_kitchen(
    client: AsyncClient,
) -> None:
    """Nada llega a la cuenta sin llegar a la cocina.

    Con el resto del pedido ya enrutado, lo añadido se manda solo: si se quedara `pending`,
    el cliente pagaría unas papas que nadie cocinó.
    """
    seeded, token = await _seed_all(client)
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
        item = (await session.execute(select(OrderItemModel).limit(1))).scalar_one()
        session.add(
            OrderItemStationModel(
                tenant_id=tenant_id,
                branch_id=seeded.branch_id,
                order_item_id=item.id,
                kitchen_station_id=station.id,
                tasks=[],
            )
        )
        await session.execute(
            update(OrderModel)
            .where(OrderModel.edit_token == token)
            .values(kitchen_state="in_kitchen")
        )
        await session.commit()
        already_cooking = item.id

    resp = await client.patch(
        f"/storefront/orders/{token}",
        json={"add": [{"variantId": str(seeded.variant_id), "quantity": 1}]},
    )
    assert resp.status_code == 200, resp.text

    async with SessionFactory() as session:
        routed = set(
            (
                await session.execute(select(OrderItemStationModel.order_item_id))
            ).scalars()
        )
        items = set(
            (await session.execute(select(OrderItemModel.id))).scalars()
        )
    assert already_cooking in routed
    assert routed == items, "la línea nueva se quedó sin ticket de cocina"


async def test_the_token_only_opens_its_own_order(client: AsyncClient) -> None:
    seeded, first = await _seed_all(client)
    second = await _order_with_token(client, seeded)
    assert first != second

    async with SessionFactory() as session:
        second_id = (
            await session.execute(
                select(OrderModel.id).where(OrderModel.edit_token == second)
            )
        ).scalar_one()

    view = (await client.get(f"/storefront/orders/{first}")).json()
    assert uuid.UUID(view["orderId"]) != second_id
    assert len(view["lines"]) == 1


async def test_a_token_cannot_touch_a_line_of_another_order(
    client: AsyncClient,
) -> None:
    seeded, mine = await _seed_all(client)
    theirs = await _order_with_token(client, seeded)
    their_line = (await client.get(f"/storefront/orders/{theirs}")).json()["lines"][0]

    resp = await client.patch(
        f"/storefront/orders/{mine}",
        json={"edit": [{"itemId": their_line["itemId"], "quantity": 2}]},
    )
    assert resp.status_code == 404

    untouched = (await client.get(f"/storefront/orders/{theirs}")).json()
    assert untouched["lines"][0]["quantity"] == 1


async def test_another_tenant_cannot_open_the_link(client: AsyncClient) -> None:
    """El token es global, pero se resuelve dentro del tenant del subdominio.

    Mismo 404 que un token inventado: si el otro tenant recibiera algo distinto, el enlace
    serviría para averiguar en qué negocio existe un pedido.
    """
    _, token = await _seed_all(client)
    async with SessionFactory() as session:
        session.add(TenantModel(slug="otro", name="Otro", is_active=True))
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url=f"http://otro.api.local{API_PREFIX}"
    ) as stranger:
        resp = await stranger.get(f"/storefront/orders/{token}")
        unknown = await stranger.get(f"/storefront/orders/{'z' * 43}")
    assert resp.status_code == 404
    assert resp.json() == unknown.json()


async def test_removing_and_cancelling_have_no_verb_at_all(client: AsyncClient) -> None:
    """Quitar y cancelar no se rechazan con un motivo: no existen en esta superficie.

    El cuerpo ignora lo que no reconoce, así que un cliente que invente `remove` obtiene una
    edición vacía — nunca un borrado a medias.
    """
    seeded, token = await _seed_all(client)
    before = (await client.get(f"/storefront/orders/{token}")).json()
    item_id = before["lines"][0]["itemId"]

    resp = await client.patch(
        f"/storefront/orders/{token}",
        json={
            "remove": [{"itemId": item_id}],
            "cancel": True,
            "edit": [{"itemId": item_id, "removeAddonIds": [str(seeded.addon_id)]}],
        },
    )
    assert resp.status_code == 200, resp.text
    after = (await client.get(f"/storefront/orders/{token}")).json()
    assert after["lines"] == before["lines"]
    assert after["status"] == "open"


async def test_the_edit_is_signed_by_the_system_employee_and_says_the_customer_asked(
    client: AsyncClient,
) -> None:
    seeded, token = await _seed_all(client)

    resp = await client.patch(
        f"/storefront/orders/{token}",
        json={"add": [{"variantId": str(seeded.variant_id), "quantity": 1}]},
    )
    assert resp.status_code == 200, resp.text

    async with SessionFactory() as session:
        order = (
            await session.execute(
                select(OrderModel).where(OrderModel.edit_token == token)
            )
        ).scalar_one()
        entry = (
            await session.execute(
                select(AuditLogModel).where(
                    AuditLogModel.action == "storefront.order_edited"
                )
            )
        ).scalar_one()

    # Firma el empleado de sistema (el mismo que firma el pedido); el detalle aclara que la
    # decisión fue del cliente. Las dos cosas, porque una comanda necesita un empleado y el
    # cliente no lo es.
    assert entry.actor_id == order.employee_id
    assert entry.entity_type == "order"
    assert entry.entity_id == order.id
    assert entry.branch_id == order.branch_id
    assert "canal=enlace_cliente" in (entry.detail or "")
    assert "28000.00->56000.00" in (entry.detail or "")
    # Nunca el token: un rastro que lo copiara sería la llave del pedido que describe.
    assert token not in (entry.detail or "")
