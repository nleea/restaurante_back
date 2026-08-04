"""Los dos recorridos completos, de punta a punta.

Las piezas están probadas por separado en los otros ficheros. Esto prueba que **encajan**, que es
otra cosa: un cambio que rompa el engarce puede dejar verdes todas las pruebas de unidad.

1. **Con WhatsApp**: pide por transferencia → recibe el aviso de que falta el pago → manda la foto
   → un empleado la usa como comprobante → verifica → cocina y "confirmamos tu pago".
2. **En frío**: pide por la web sin haber escrito nunca → escribe por primera vez → el saludo
   reconoce que tiene un pedido esperando pago, sin leer lo que escribió.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.messaging.infrastructure.models import (
    WhatsAppAutoreplySettingsModel,
    WhatsAppContactModel,
    WhatsAppConversationModel,
    WhatsAppMessageModel,
)
from restaurante.modules.orders.infrastructure.models import (
    OrderModel,
    OrderPaymentClaimModel,
    OrderPaymentModel,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.domain.phones import normalize_phone
from tests.conftest import TEST_EMAIL
from tests.modules._cash import seed_open_cash_session
from tests.modules.messaging.conftest import (
    SECRET_HEADER,
    create_branch,
    create_employee,
    create_session_row,
    demo_tenant_id,
    grant_only,
    login,
    post_inbound,
)

PHONE = "+573001112233"
JID = "573001112233@s.whatsapp.net"
AWAITING_TEXT = "¡Hola! Vimos tu pedido {order_number} por {order_total}. Manda el comprobante."


async def _greeting(**over: object) -> None:
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        row = WhatsAppAutoreplySettingsModel(tenant_id=tenant_id, greeting_enabled=True)
        for key, value in over.items():
            setattr(row, key, value)
        s.add(row)
        await s.commit()


async def _prepaid_order(branch_id: uuid.UUID, employee_id: uuid.UUID) -> uuid.UUID:
    """Un pedido por transferencia, sin pagar, del contacto que escribió."""
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        contact = (await s.execute(select(WhatsAppContactModel))).scalars().first()
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
            whatsapp_contact_id=contact.id if contact else None,
            created_at=datetime.now(UTC),
        )
        s.add(order)
        await s.commit()
        return order.id


async def _send_photo(client: AsyncClient, message_id: str) -> None:
    await client.post(
        "/webhooks/whatsapp/inst-centro",
        headers=SECRET_HEADER,
        json={
            "event": "messages.upsert",
            "instance": "inst-centro",
            "data": {
                "key": {"id": message_id, "remoteJid": JID, "fromMe": False},
                "messageType": "imageMessage",
                "message": {
                    "imageMessage": {
                        "mimetype": "image/jpeg",
                        "fileLength": 90_000,
                        "caption": "aquí va mi comprobante",
                    }
                },
            },
        },
    )


# --- 1. El recorrido con WhatsApp -------------------------------------------
async def test_the_whole_journey_from_photo_to_kitchen(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    employee_id = await create_employee(branch, TEST_EMAIL)
    await seed_open_cash_session(branch, employee_id)
    await _greeting()
    # El cliente escribe (crea contacto y conversación) y pide.
    await post_inbound(client, "inst-centro", message_id="in-1", phone=PHONE)
    order_id = await _prepaid_order(branch, employee_id)

    # 1. Manda la foto: entra al hilo con su pie de foto y su archivo.
    await _send_photo(client, "img-1")
    async with SessionFactory() as s:
        photo = (
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
        conversation = (
            (await s.execute(select(WhatsAppConversationModel))).scalars().first()
        )
    assert photo is not None, "la foto tiene que estar guardada en el hilo"
    assert photo.content == "aquí va mi comprobante"

    await grant_only(["messaging.read", "orders.pay", "orders.read", "orders.update"])
    headers = await login(client)

    # 2. Una PERSONA la usa como comprobante del pedido.
    used = await client.post(
        f"/messaging/conversations/{conversation.id}/messages/{photo.id}/use-as-proof",
        params={"branch_id": str(branch)},
        headers=headers,
        json={"order_id": str(order_id), "amount": "46000"},
    )
    assert used.status_code == 204, used.text

    # 3. El hilo ya dice que ese archivo está usado, y por qué pedido.
    thread = await client.get(
        f"/messaging/conversations/{conversation.id}",
        params={"branch_id": str(branch)},
        headers=headers,
    )
    labels = [m["proof_of_order"] for m in thread.json()["messages"]]
    assert order_id.hex[:8].upper() in labels

    # 4. Verificar: registra el pago y manda el pedido a cocina, en un gesto.
    verified = await client.post(
        f"/orders/{order_id}/verify-payment",
        headers=headers,
        json={"employee_id": str(employee_id)},
    )
    assert verified.status_code == 200, verified.text

    async with SessionFactory() as s:
        claims = list((await s.execute(select(OrderPaymentClaimModel))).scalars())
        payments = list((await s.execute(select(OrderPaymentModel))).scalars())
    assert [c.status for c in claims] == ["accepted"]
    assert len(payments) == 1 and payments[0].amount == Decimal("46000")

    # 5. Y el cliente se entera de que su pago quedó confirmado.
    bodies = [body for _phone, body in fake_bridge.sent]
    assert any("Confirmamos tu pago" in b for b in bodies)


async def test_the_same_photo_cannot_pay_two_orders(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    """El segundo intento se rechaza diciendo lo que pasa, no con un fallo técnico."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    employee_id = await create_employee(branch, TEST_EMAIL)
    await post_inbound(client, "inst-centro", message_id="in-1", phone=PHONE)
    first = await _prepaid_order(branch, employee_id)
    second = await _prepaid_order(branch, employee_id)
    await _send_photo(client, "img-1")
    async with SessionFactory() as s:
        photo = (
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
        conversation = (
            (await s.execute(select(WhatsAppConversationModel))).scalars().first()
        )
    await grant_only(["messaging.read", "orders.pay"])
    headers = await login(client)
    url = f"/messaging/conversations/{conversation.id}/messages/{photo.id}/use-as-proof"

    ok = await client.post(
        url,
        params={"branch_id": str(branch)},
        headers=headers,
        json={"order_id": str(first), "amount": "46000"},
    )
    again = await client.post(
        url,
        params={"branch_id": str(branch)},
        headers=headers,
        json={"order_id": str(second), "amount": "46000"},
    )

    assert ok.status_code == 204
    assert again.status_code == 409, again.text
    assert "ya está usado" in again.json()["detail"]


# --- 2. El recorrido en frío -------------------------------------------------
async def test_a_web_customer_who_never_wrote_is_greeted_with_their_order(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    """Sin esto, quien manda su comprobante en frío recibe "mira nuestra carta" encima.

    Y la variante se elige por el ESTADO del pedido: el mensaje del cliente aquí es una palabra
    cualquiera, no una pista.
    """
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    employee_id = await create_employee(branch, TEST_EMAIL)
    await _greeting(greeting_awaiting_payment_text=AWAITING_TEXT)

    # Pidió por la web: existe el contacto (el checkout guarda su teléfono) pero NUNCA escribió,
    # así que no hay conversación y no se le puede avisar de nada.
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        # El teléfono se guarda NORMALIZADO, que es como lo escribe el canal. Insertarlo con el
        # `+` crearía un segundo contacto cuando el cliente escriba, y el pedido colgaría del otro.
        s.add(
            WhatsAppContactModel(
                tenant_id=tenant_id, phone=normalize_phone(PHONE), name="Nelson"
            )
        )
        await s.commit()
    order_id = await _prepaid_order(branch, employee_id)
    assert fake_bridge.sent == [], "a quien nunca escribió no se le inicia una conversación"

    # Escribe por primera vez, con el texto prellenado del enlace.
    await post_inbound(
        client,
        "inst-centro",
        message_id="in-1",
        phone=PHONE,
        text=f"Hola, mi pedido {order_id.hex[:8].upper()} por $46.000.",
    )

    _phone, greeting = fake_bridge.sent[0]
    assert order_id.hex[:8].upper() in greeting
    assert "$46.000" in greeting
    assert "Bienvenido" not in greeting
