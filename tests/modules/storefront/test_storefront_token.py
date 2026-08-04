"""El token del enlace de WhatsApp: precarga el checkout y ata el pedido al chat.

Dos reglas gobiernan todo lo de aquí:

1. **El token precarga, no autentica.** Lo que devuelve es lo que el cliente puede
   corregir a mano en el formulario. Resuelve a un CONTACTO, nunca a un pedido, así que
   un enlace filtrado no puede leer el historial de nadie.
2. **Nunca cuesta la venta.** Ausente, vencido, desconocido o de otra sede: el pedido se
   crea igual e identifica al cliente por teléfono, como cualquier pedido web.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.messaging.infrastructure.models import (
    WhatsAppContactModel,
    WhatsAppConversationModel,
)
from restaurante.modules.orders.infrastructure.models import OrderModel
from restaurante.shared.database import SessionFactory
from tests.modules._cash import seed_open_cash_session
from tests.modules.storefront._seed import (
    SeededMenu,
    demo_tenant_id,
    seed_menu,
    seed_primary_branch,
)

_PHONE = "+573001112233"


async def _seed_token(
    branch_id: uuid.UUID,
    *,
    token: str = "tok-vivo",
    hours: int = 24,
    name: str | None = "Ana Pérez",
) -> uuid.UUID:
    """Un contacto con su conversación y un token. `hours` negativo lo deja vencido."""
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        contact = WhatsAppContactModel(
            tenant_id=tenant_id, phone=_PHONE, name=name
        )
        s.add(contact)
        await s.flush()
        s.add(
            WhatsAppConversationModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                whatsapp_contact_id=contact.id,
                status="greeted",
                store_token=token,
                store_token_expires_at=datetime.now(UTC) + timedelta(hours=hours),
            )
        )
        await s.commit()
        return contact.id


def _payload(seeded: SeededMenu, **over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "customer": {"name": "Ana Pérez", "phone": _PHONE},
        "fulfillment": {"type": "pickup"},
        "paymentMethod": "efectivo",
        "lines": [{"variantId": str(seeded.variant_id), "quantity": 1}],
    }
    payload.update(over)
    return payload


async def _order_contact(order_id: uuid.UUID) -> uuid.UUID | None:
    async with SessionFactory() as s:
        return (
            await s.execute(
                select(OrderModel.whatsapp_contact_id).where(OrderModel.id == order_id)
            )
        ).scalar_one()


# --- Resolver el token --------------------------------------------------------
async def test_a_live_token_resolves_twice_within_its_life(
    client: AsyncClient,
) -> None:
    """Reutilizable a propósito: un token de un solo uso se lee como sistema roto."""
    branch_id = await seed_primary_branch(code="centro")
    await _seed_token(branch_id)

    first = await client.get("/storefront/session/tok-vivo")
    second = await client.get("/storefront/session/tok-vivo")

    assert first.status_code == 200, first.text
    assert second.status_code == 200
    body = first.json()
    assert body["phone"] == _PHONE
    assert body["name"] == "Ana Pérez"
    assert body["branchCode"] == "centro"
    # Y nada más: ni pedidos, ni id de contacto, ni historial.
    assert set(body) == {"name", "phone", "branchCode"}


async def test_an_expired_token_is_indistinguishable_from_an_unknown_one(
    client: AsyncClient,
) -> None:
    """Quien pruebe enlaces no debe aprender si alguno existió alguna vez."""
    branch_id = await seed_primary_branch(code="centro")
    await _seed_token(branch_id, token="tok-viejo", hours=-1)

    expired = await client.get("/storefront/session/tok-viejo")
    unknown = await client.get("/storefront/session/tok-inventado")

    assert expired.status_code == 404
    assert unknown.status_code == 404
    assert expired.json()["code"] == unknown.json()["code"]


# --- Atar el pedido al chat ---------------------------------------------------
async def test_a_tokenised_order_links_the_contact(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch(code="centro")
    seeded = await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)
    contact_id = await _seed_token(branch_id)

    resp = await client.post(
        "/storefront/orders", json=_payload(seeded, storeToken="tok-vivo")
    )

    assert resp.status_code == 201, resp.text
    order_id = uuid.UUID(resp.json()["orderId"])
    assert await _order_contact(order_id) == contact_id


async def test_a_token_less_order_still_creates_and_matches_by_phone(
    client: AsyncClient,
) -> None:
    branch_id = await seed_primary_branch(code="centro")
    seeded = await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)
    await _seed_token(branch_id)

    resp = await client.post("/storefront/orders", json=_payload(seeded))

    assert resp.status_code == 201, resp.text
    order_id = uuid.UUID(resp.json()["orderId"])
    # Sin token no se ata, pero el pedido existe y tiene su cliente por teléfono.
    assert await _order_contact(order_id) is None
    async with SessionFactory() as s:
        customer_id = (
            await s.execute(
                select(OrderModel.customer_id).where(OrderModel.id == order_id)
            )
        ).scalar_one()
    assert customer_id is not None


async def test_an_expired_token_does_not_block_the_order(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch(code="centro")
    seeded = await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)
    await _seed_token(branch_id, token="tok-viejo", hours=-1)

    resp = await client.post(
        "/storefront/orders", json=_payload(seeded, storeToken="tok-viejo")
    )

    assert resp.status_code == 201, resp.text
    assert await _order_contact(uuid.UUID(resp.json()["orderId"])) is None


async def test_an_unknown_token_does_not_block_the_order(client: AsyncClient) -> None:
    branch_id = await seed_primary_branch(code="centro")
    seeded = await seed_menu(branch_id)
    await seed_open_cash_session(branch_id)

    resp = await client.post(
        "/storefront/orders", json=_payload(seeded, storeToken="nada-de-nada")
    )

    assert resp.status_code == 201, resp.text
    assert await _order_contact(uuid.UUID(resp.json()["orderId"])) is None


async def test_a_branch_mismatched_token_does_not_link(client: AsyncClient) -> None:
    """El enlace era de Centro y el pedido es de Norte: atarlo mandaría los avisos al
    chat equivocado."""
    centro = await seed_primary_branch(code="centro")
    norte = await seed_primary_branch(code="norte", is_primary=False)
    seeded = await seed_menu(norte)
    await seed_open_cash_session(norte)
    await _seed_token(centro)

    resp = await client.post(
        "/storefront/norte/orders", json=_payload(seeded, storeToken="tok-vivo")
    )

    assert resp.status_code == 201, resp.text
    assert await _order_contact(uuid.UUID(resp.json()["orderId"])) is None
