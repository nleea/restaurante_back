"""Public storefront order intake: real OPEN/unpaid orders, pending (not fired)."""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.customers.infrastructure.models import CustomerModel
from restaurante.modules.delivery.infrastructure.models import OrderDeliveryModel
from restaurante.modules.orders.infrastructure.models import (
    OrderItemAddonModel,
    OrderItemModel,
    OrderModel,
    OrderPaymentModel,
)
from restaurante.shared.database import SessionFactory
from tests.modules._cash import seed_open_cash_session
from tests.modules.storefront._seed import (
    SeededMenu,
    seed_delivery_ready,
    seed_menu,
    seed_primary_branch,
)


def _pickup_payload(seeded: SeededMenu, **over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "customer": {"name": "Ana Pérez", "phone": "3001234567"},
        "fulfillment": {"type": "pickup"},
        "paymentMethod": "efectivo",
        "lines": [
            {
                "variantId": str(seeded.variant_id),
                "quantity": 2,
                "addonIds": [str(seeded.addon_id)],
                "removedIngredients": ["Cebolla"],
                "note": "bien picante",
            }
        ],
    }
    payload.update(over)
    return payload


async def test_pickup_order_created_takeaway_with_items_and_addons(
    client: AsyncClient,
) -> None:
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)

    resp = await client.post("/storefront/orders", json=_pickup_payload(seeded))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    order_id = uuid.UUID(body["orderId"])
    # La etiqueta corta, NO el uuid. Antes se devolvía el id entero y el cliente veía dos números
    # distintos para el mismo pedido: `C328A1B2` en su WhatsApp y `c328a1b2-4f5e-…` aquí.
    assert body["orderNumber"] == order_id.hex[:8].upper()
    assert body["status"] == "open"

    async with SessionFactory() as session:
        order = (
            await session.execute(select(OrderModel).where(OrderModel.id == order_id))
        ).scalar_one()
        assert order.channel == "takeaway"
        assert order.payment_method == "efectivo"
        assert order.customer_id is not None

        items = (
            await session.execute(
                select(OrderItemModel).where(OrderItemModel.order_id == order_id)
            )
        ).scalars().all()
        assert len(items) == 1
        assert items[0].quantity == 2

        addons = (
            await session.execute(
                select(OrderItemAddonModel).where(
                    OrderItemAddonModel.order_item_id == items[0].id
                )
            )
        ).scalars().all()
        assert len(addons) == 1


async def test_removals_and_note_folded_into_item_note(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)

    resp = await client.post("/storefront/orders", json=_pickup_payload(seeded))
    assert resp.status_code == 201, resp.text
    order_id = uuid.UUID(resp.json()["orderId"])

    async with SessionFactory() as session:
        item = (
            await session.execute(
                select(OrderItemModel).where(OrderItemModel.order_id == order_id)
            )
        ).scalar_one()
        assert item.notes == "Sin Cebolla · bien picante"


async def test_payment_method_stored_without_order_payment_row(
    client: AsyncClient,
) -> None:
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)

    resp = await client.post(
        "/storefront/orders",
        json=_pickup_payload(seeded, paymentMethod="transferencia"),
    )
    assert resp.status_code == 201, resp.text
    order_id = uuid.UUID(resp.json()["orderId"])

    async with SessionFactory() as session:
        order = (
            await session.execute(select(OrderModel).where(OrderModel.id == order_id))
        ).scalar_one()
        assert order.payment_method == "transferencia"

        payments = (
            await session.execute(
                select(OrderPaymentModel).where(OrderPaymentModel.order_id == order_id)
            )
        ).scalars().all()
        assert payments == []  # intent only — no money received at intake


async def test_order_lands_pending_not_fired(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)

    resp = await client.post("/storefront/orders", json=_pickup_payload(seeded))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "open"
    order_id = uuid.UUID(body["orderId"])

    async with SessionFactory() as session:
        order = (
            await session.execute(select(OrderModel).where(OrderModel.id == order_id))
        ).scalar_one()
        assert order.kitchen_state == "none"  # not routed to the kitchen

        item = (
            await session.execute(
                select(OrderItemModel).where(OrderItemModel.order_id == order_id)
            )
        ).scalar_one()
        assert item.status == "pending"  # awaiting staff confirmation


async def test_delivery_order_attaches_delivery(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)
    await seed_delivery_ready(branch_id)

    payload = _pickup_payload(
        seeded,
        fulfillment={
            "type": "delivery",
            "addressText": "Calle 1 #2-3",
            "latitude": 11.54,
            "longitude": -72.9,
            "reference": "casa azul",
        },
    )
    resp = await client.post("/storefront/orders", json=payload)
    assert resp.status_code == 201, resp.text
    order_id = uuid.UUID(resp.json()["orderId"])

    async with SessionFactory() as session:
        order = (
            await session.execute(select(OrderModel).where(OrderModel.id == order_id))
        ).scalar_one()
        assert order.channel == "delivery"

        delivery = (
            await session.execute(
                select(OrderDeliveryModel).where(
                    OrderDeliveryModel.order_id == order_id
                )
            )
        ).scalar_one()
        assert "Calle 1 #2-3" in delivery.address_text


class TestDeliveryDefersThePaymentMethod:
    """El cliente no elige cómo pagar un total que todavía no existe.

    Un domicilio nace sin precio de domicilio, así que el checkout ya no puede pedir el medio
    de pago: lo recoge el enlace que llega por WhatsApp con el total ya cotizado.
    """

    async def test_a_delivery_is_accepted_with_no_payment_method(
        self, client: AsyncClient
    ) -> None:
        branch_id = await seed_primary_branch()
        seeded = await seed_menu(branch_id)
        await seed_open_cash_session(branch_id)
        await seed_delivery_ready(branch_id)

        payload = _pickup_payload(
            seeded,
            fulfillment={
                "type": "delivery",
                "addressText": "Calle 1 #2-3",
                "latitude": 11.54,
                "longitude": -72.9,
            },
        )
        payload.pop("paymentMethod")

        resp = await client.post("/storefront/orders", json=payload)

        assert resp.status_code == 201, resp.text
        order_id = uuid.UUID(resp.json()["orderId"])
        async with SessionFactory() as session:
            order = (
                await session.execute(
                    select(OrderModel).where(OrderModel.id == order_id)
                )
            ).scalar_one()
            assert order.payment_method is None
            # Y no nace cobrado: el enlace de pago es lo único que registra dinero.
            payments = (
                await session.execute(
                    select(OrderPaymentModel).where(
                        OrderPaymentModel.order_id == order_id
                    )
                )
            ).scalars().all()
            assert payments == []

    async def test_a_delivery_ignores_a_payment_method_it_is_sent(
        self, client: AsyncClient
    ) -> None:
        """Un cliente viejo en caché, o un curioso con curl, no puede fijar el intento antes
        de tiempo: el total que vería el enlace de pago dejaría de cuadrar con lo elegido."""
        branch_id = await seed_primary_branch()
        seeded = await seed_menu(branch_id)
        await seed_open_cash_session(branch_id)
        await seed_delivery_ready(branch_id)

        payload = _pickup_payload(
            seeded,
            fulfillment={"type": "delivery", "addressText": "Calle 1 #2-3"},
            paymentMethod="transfer",
        )

        resp = await client.post("/storefront/orders", json=payload)

        assert resp.status_code == 201, resp.text
        async with SessionFactory() as session:
            order = (
                await session.execute(
                    select(OrderModel).where(
                        OrderModel.id == uuid.UUID(resp.json()["orderId"])
                    )
                )
            ).scalar_one()
            assert order.payment_method is None

    async def test_pickup_still_requires_one(self, client: AsyncClient) -> None:
        """Recoger no espera ninguna cotización: su total ya es el definitivo."""
        branch_id = await seed_primary_branch()
        seeded = await seed_menu(branch_id)
        await seed_open_cash_session(branch_id)

        payload = _pickup_payload(seeded)
        payload.pop("paymentMethod")

        resp = await client.post("/storefront/orders", json=payload)

        assert resp.status_code == 422, resp.text


async def test_same_phone_reuses_one_customer(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)

    first = await client.post("/storefront/orders", json=_pickup_payload(seeded))
    second = await client.post("/storefront/orders", json=_pickup_payload(seeded))
    assert first.status_code == 201
    assert second.status_code == 201

    async with SessionFactory() as session:
        customers = (
            await session.execute(select(CustomerModel))
        ).scalars().all()
        assert len(customers) == 1

        first_order = (
            await session.execute(
                select(OrderModel).where(
                    OrderModel.id == uuid.UUID(first.json()["orderId"])
                )
            )
        ).scalar_one()
        second_order = (
            await session.execute(
                select(OrderModel).where(
                    OrderModel.id == uuid.UUID(second.json()["orderId"])
                )
            )
        ).scalar_one()
        assert first_order.customer_id == second_order.customer_id


async def test_empty_cart_is_rejected(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)

    resp = await client.post("/storefront/orders", json=_pickup_payload(seeded, lines=[]))
    assert resp.status_code == 422


async def test_unknown_variant_is_rejected(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch()
    await seed_menu(branch_id)

    payload = {
        "customer": {"name": "Ana", "phone": "3009999999"},
        "fulfillment": {"type": "pickup"},
        "paymentMethod": "efectivo",
        "lines": [{"variantId": str(uuid.uuid4()), "quantity": 1}],
    }
    resp = await client.post("/storefront/orders", json=payload)
    assert resp.status_code == 422


async def test_missing_customer_fields_rejected(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)

    resp = await client.post(
        "/storefront/orders",
        json=_pickup_payload(seeded, customer={"name": "", "phone": ""}),
    )
    assert resp.status_code == 422


# --- Compartir la ubicación es decir dónde vives -----------------------------
async def test_delivery_with_only_a_shared_location_is_accepted(
    client: AsyncClient,
) -> None:
    """El bug: dar la ubicación y que el pedido se rechazara por no escribir dirección.

    El pin es MÁS preciso que cualquier dirección escrita (que además habría que
    geocodificar), y el domiciliario lleva el mapa. Rechazarlo era pedirle al cliente que
    escribiera algo que el sistema ya sabía mejor que él.
    """
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)
    await seed_delivery_ready(branch_id)

    payload = _pickup_payload(
        seeded,
        fulfillment={
            "type": "delivery",
            "latitude": 11.54321,
            "longitude": -72.90678,
        },
    )
    resp = await client.post("/storefront/orders", json=payload)

    assert resp.status_code == 201, resp.text
    order_id = uuid.UUID(resp.json()["orderId"])
    async with SessionFactory() as session:
        delivery = (
            await session.execute(
                select(OrderDeliveryModel).where(
                    OrderDeliveryModel.order_id == order_id
                )
            )
        ).scalar_one()
    # La comanda no sale en blanco: dice que hay que guiarse por el pin, y lleva las
    # coordenadas por si el mapa falla.
    assert "Ubicación compartida" in delivery.address_text
    assert "11.54321" in delivery.address_text
    # Y el pin se guarda tal cual: es el dato bueno.
    assert float(delivery.latitude) == 11.54321
    assert float(delivery.longitude) == -72.90678


async def test_a_shared_location_with_a_reference_keeps_the_reference(
    client: AsyncClient,
) -> None:
    """Lo que el cliente escribió gana: "casa azul" le sirve más al domiciliario."""
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)
    await seed_delivery_ready(branch_id)

    payload = _pickup_payload(
        seeded,
        fulfillment={
            "type": "delivery",
            "latitude": 11.54,
            "longitude": -72.9,
            "reference": "casa azul, portón negro",
        },
    )
    resp = await client.post("/storefront/orders", json=payload)

    assert resp.status_code == 201, resp.text
    async with SessionFactory() as session:
        delivery = (
            await session.execute(
                select(OrderDeliveryModel).where(
                    OrderDeliveryModel.order_id
                    == uuid.UUID(resp.json()["orderId"])
                )
            )
        ).scalar_one()
    assert delivery.address_text == "casa azul, portón negro"
    assert float(delivery.latitude) == 11.54


async def test_delivery_with_neither_text_nor_location_is_still_refused(
    client: AsyncClient,
) -> None:
    """Sin dirección y sin pin no hay a dónde llevarlo. Eso sí se rechaza."""
    branch_id = await seed_primary_branch()
    seeded = await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)
    await seed_delivery_ready(branch_id)

    payload = _pickup_payload(seeded, fulfillment={"type": "delivery"})
    resp = await client.post("/storefront/orders", json=payload)

    assert resp.status_code == 422, resp.text
    assert "ubicación" in resp.json()["detail"].lower()


class TestABranchThatCannotQuoteRefusesDeliveries:
    """El fallo que esta guarda evita es SILENCIOSO, y por eso hace falta una guarda.

    Sin bandas de tarifa la cadena entera corre igual: el pedido se acepta, se le da las gracias
    al cliente, el worker lo recoge, no encuentra con qué ponerle precio y lo marca no cotizable.
    Nadie cobra, nadie escribe, y el cliente espera un enlace que no existe. Desde fuera se ve
    como un restaurante que funciona y va lento.
    """

    def _delivery_payload(self, seeded: SeededMenu) -> dict[str, Any]:
        payload = _pickup_payload(
            seeded, fulfillment={"type": "delivery", "addressText": "Calle 1 #2-3"}
        )
        payload.pop("paymentMethod")
        return payload

    async def test_without_tariff_bands_the_delivery_is_refused(
        self, client: AsyncClient
    ) -> None:
        branch_id = await seed_primary_branch()
        seeded = await seed_menu(branch_id)
        await seed_open_cash_session(branch_id)
        # Sin `seed_delivery_ready`: la sede no tiene ni pin ni tarifas.

        resp = await client.post("/storefront/orders", json=self._delivery_payload(seeded))

        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        # Lo que el CLIENTE necesita: hoy no, y qué puede hacer. No un problema del negocio.
        assert "no estamos tomando pedidos a domicilio" in detail.lower()
        assert "recoger" in detail.lower()
        assert "tarifa" not in detail.lower()

    async def test_a_refused_delivery_leaves_nothing_half_created(
        self, client: AsyncClient
    ) -> None:
        branch_id = await seed_primary_branch()
        seeded = await seed_menu(branch_id)
        await seed_open_cash_session(branch_id)

        await client.post("/storefront/orders", json=self._delivery_payload(seeded))

        async with SessionFactory() as session:
            orders = (await session.execute(select(OrderModel))).scalars().all()
            deliveries = (
                await session.execute(select(OrderDeliveryModel))
            ).scalars().all()
        assert orders == []
        assert deliveries == []

    async def test_pickup_still_works_on_the_same_branch(
        self, client: AsyncClient
    ) -> None:
        """No repartir no es estar cerrado: el mostrador sigue tomando pedidos."""
        branch_id = await seed_primary_branch()
        seeded = await seed_menu(branch_id)
        await seed_open_cash_session(branch_id)

        resp = await client.post("/storefront/orders", json=_pickup_payload(seeded))

        assert resp.status_code == 201, resp.text

    async def test_configuring_the_branch_opens_deliveries(
        self, client: AsyncClient
    ) -> None:
        branch_id = await seed_primary_branch()
        seeded = await seed_menu(branch_id)
        await seed_open_cash_session(branch_id)
        await seed_delivery_ready(branch_id)

        resp = await client.post("/storefront/orders", json=self._delivery_payload(seeded))

        assert resp.status_code == 201, resp.text
