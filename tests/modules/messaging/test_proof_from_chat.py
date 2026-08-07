"""Un comprobante que nace de un mensaje del chat.

Lo que se prueba aquí no es que funcione: es **quién puede** y **qué se rechaza**. Dos cosas son
el change entero y las dos tienen su prueba con nombre:

- **Llegar no crea nada.** Una foto no es una declaración de pago: los clientes mandan fotos de la
  calle, memes y su cédula. Un claim automático acaba siendo un "comprobante" que es la foto de un
  perro, y entonces el mostrador aprende a ignorar el aviso.
- **Sólo pedidos de ESE contacto.** Un id de otro cliente es un salto disfrazado de comodidad.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.messaging.infrastructure.models import (
    WhatsAppContactModel,
    WhatsAppConversationModel,
    WhatsAppMessageModel,
)
from restaurante.modules.orders.infrastructure.models import (
    OrderModel,
    OrderPaymentClaimModel,
)
from restaurante.shared.database import SessionFactory
from tests.conftest import TEST_EMAIL
from tests.modules.messaging.conftest import (
    create_branch,
    create_employee,
    create_session_row,
    demo_tenant_id,
    grant_only,
    login,
    post_inbound,
)

JID = "573001112233@s.whatsapp.net"


async def _media_message(client: AsyncClient, instance_ref: str, message_id: str) -> None:
    await client.post(
        f"/webhooks/whatsapp/{instance_ref}",
        headers={"X-Webhook-Secret": "test-webhook-secret"},
        json={
            "event": "messages.upsert",
            "instance": instance_ref,
            "data": {
                "key": {"id": message_id, "remoteJid": JID, "fromMe": False},
                "messageType": "imageMessage",
                "message": {"imageMessage": {"mimetype": "image/jpeg", "fileLength": 1000}},
            },
        },
    )


async def _order(
    branch_id: uuid.UUID, employee_id: uuid.UUID, *, contact: bool = True
) -> uuid.UUID:
    """Un pedido de quien escribió (o de nadie, para probar el id ajeno).

    El empleado llega de fuera: `create_employee` ata al usuario de la demo y sólo puede haber uno
    por usuario, así que crearlo aquí choca con el que hace falta para autenticar.
    """
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        contact_row = (
            (await s.execute(select(WhatsAppContactModel))).scalars().first()
            if contact
            else None
        )
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            employee_id=employee_id,
            channel="whatsapp",
            status="open",
            payment_method="transfer",
            subtotal=Decimal("46000"),
            discount=Decimal("0"),
            total=Decimal("46000"),
            whatsapp_contact_id=contact_row.id if contact_row else None,
            created_at=datetime.now(UTC),
        )
        s.add(order)
        await s.commit()
        return order.id


async def _ids() -> tuple[uuid.UUID, uuid.UUID]:
    async with SessionFactory() as s:
        conversation = (
            (await s.execute(select(WhatsAppConversationModel))).scalars().first()
        )
        message = (
            (
                await s.execute(
                    select(WhatsAppMessageModel).where(
                        WhatsAppMessageModel.media_url.is_not(None)
                    )
                )
            )
            .scalars()
            .first()
        )
        return conversation.id, (message.id if message else uuid.uuid4())


async def _employee_of(branch_id: uuid.UUID) -> uuid.UUID:
    """El empleado que ya existe. Sirve para los pedidos extra de una misma prueba."""
    from restaurante.modules.staff.infrastructure.models import EmployeeModel

    async with SessionFactory() as s:
        return (await s.execute(select(EmployeeModel))).scalars().first().id


async def _claims() -> list[OrderPaymentClaimModel]:
    async with SessionFactory() as s:
        return list((await s.execute(select(OrderPaymentClaimModel))).scalars())


async def _wired(client: AsyncClient, media_sink) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Sede emparejada, una imagen ya guardada en el hilo, un pedido de ese contacto."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    employee_id = await create_employee(branch, TEST_EMAIL)
    await _media_message(client, "inst-centro", "m-1")
    order_id = await _order(branch, employee_id)
    conversation_id, _message_id = await _ids()
    return branch, order_id, conversation_id


# --- Llegar no crea nada -----------------------------------------------------
async def test_an_arriving_image_creates_no_claim(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    """Es la prueba que separa esto de un sistema que se cree cualquier foto."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    employee_id = await create_employee(branch, TEST_EMAIL)
    await _order(branch, employee_id)

    await _media_message(client, "inst-centro", "m-1")

    assert await _claims() == []


# --- Una persona sí, y con los dos permisos ----------------------------------
async def test_an_employee_turns_a_message_into_a_claim(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    branch, order_id, conversation_id = await _wired(client, media_sink)
    _c, message_id = await _ids()
    await grant_only(["messaging.read", "orders.pay"])
    headers = await login(client)

    resp = await client.post(
        f"/messaging/conversations/{conversation_id}/messages/{message_id}/use-as-proof",
        params={"branch_id": str(branch)},
        headers=headers,
        json={"order_id": str(order_id), "amount": "46000"},
    )

    assert resp.status_code == 204, resp.text
    claims = await _claims()
    assert len(claims) == 1
    # El claim es indistinguible de uno subido por el cliente: lleva el archivo y está pendiente.
    assert claims[0].proof_url == media_sink.url
    assert claims[0].status == "pending"
    assert claims[0].order_id == order_id


async def test_the_eligible_orders_carry_the_balance(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    """Sin el saldo, quien pulsa tiene que ir a buscar cuánto se debía."""
    branch, order_id, conversation_id = await _wired(client, media_sink)
    await grant_only(["messaging.read", "orders.pay"])
    headers = await login(client)

    resp = await client.get(
        f"/messaging/conversations/{conversation_id}/eligible-orders",
        params={"branch_id": str(branch)},
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["order_id"] == str(order_id)
    assert body[0]["number"] == order_id.hex[:8].upper()
    assert Decimal(body[0]["balance"]) == Decimal("46000")


# --- Lo que se rechaza -------------------------------------------------------
async def test_attending_is_not_enough(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    """Crear un claim es un paso del camino del dinero, no de la atención."""
    branch, order_id, conversation_id = await _wired(client, media_sink)
    _c, message_id = await _ids()
    await grant_only(["messaging.read", "messaging.attend"])
    headers = await login(client)

    resp = await client.post(
        f"/messaging/conversations/{conversation_id}/messages/{message_id}/use-as-proof",
        params={"branch_id": str(branch)},
        headers=headers,
        json={"order_id": str(order_id), "amount": "46000"},
    )

    assert resp.status_code == 403
    assert await _claims() == []


async def test_another_customers_order_is_refused(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    """Aceptar un id ajeno sería un salto entre clientes disfrazado de comodidad."""
    branch, _own_order, conversation_id = await _wired(client, media_sink)
    _c, message_id = await _ids()
    stranger = await _order(branch, await _employee_of(branch), contact=False)
    await grant_only(["messaging.read", "orders.pay"])
    headers = await login(client)

    resp = await client.post(
        f"/messaging/conversations/{conversation_id}/messages/{message_id}/use-as-proof",
        params={"branch_id": str(branch)},
        headers=headers,
        json={"order_id": str(stranger), "amount": "46000"},
    )

    assert resp.status_code == 404
    assert await _claims() == []


async def test_a_message_without_a_file_is_refused(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    employee_id = await create_employee(branch, TEST_EMAIL)
    await post_inbound(client, "inst-centro", message_id="t-1", text="hola")
    order_id = await _order(branch, employee_id)
    async with SessionFactory() as s:
        conversation = (
            (await s.execute(select(WhatsAppConversationModel))).scalars().first()
        )
        message = (await s.execute(select(WhatsAppMessageModel))).scalars().first()
        conversation_id, message_id = conversation.id, message.id
    await grant_only(["messaging.read", "orders.pay"])
    headers = await login(client)

    resp = await client.post(
        f"/messaging/conversations/{conversation_id}/messages/{message_id}/use-as-proof",
        params={"branch_id": str(branch)},
        headers=headers,
        json={"order_id": str(order_id), "amount": "46000"},
    )

    assert resp.status_code == 422
    assert await _claims() == []


async def test_a_message_from_another_conversation_is_refused(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    branch, order_id, conversation_id = await _wired(client, media_sink)
    await grant_only(["messaging.read", "orders.pay"])
    headers = await login(client)

    resp = await client.post(
        f"/messaging/conversations/{conversation_id}/messages/{uuid.uuid4()}/use-as-proof",
        params={"branch_id": str(branch)},
        headers=headers,
        json={"order_id": str(order_id), "amount": "46000"},
    )

    assert resp.status_code == 404
