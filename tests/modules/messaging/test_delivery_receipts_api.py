"""El acuse entrando por el webhook y subiendo el estado de un mensaje nuestro.

Lo que se prueba aquí no es la escala —eso es `test_delivery_receipts.py`, sin base— sino que el
acuse llegue a la fila correcta y a ninguna otra: el mensaje nuestro y no el del cliente, el de
este tenant y no el del vecino, y sin dejar nada en el hilo.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.messaging.infrastructure.models import (
    WhatsAppConversationModel,
    WhatsAppMessageModel,
)
from restaurante.shared.database import SessionFactory
from tests.modules.messaging.conftest import WEBHOOK_SECRET

SENT_ID = "3EB0C1D2E3F4"


async def post_receipt(
    client: AsyncClient,
    instance_ref: str,
    *,
    key_id: str = SENT_ID,
    status: str = "DELIVERY_ACK",
    from_me: bool = True,
) -> Any:
    """El sobre de `MESSAGES_UPDATE` tal y como lo manda Evolution v2.3.7."""
    return await client.post(
        f"/webhooks/whatsapp/{instance_ref}",
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
        json={
            "event": "messages.update",
            "instance": instance_ref,
            "data": {
                "keyId": key_id,
                "remoteJid": "573001112233@s.whatsapp.net",
                "fromMe": from_me,
                "status": status,
                "instanceId": "b7d1",
            },
        },
    )


async def _state_of(provider_message_id: str) -> str | None:
    async with SessionFactory() as session:
        row = (
            await session.execute(
                select(WhatsAppMessageModel).where(
                    WhatsAppMessageModel.provider_message_id == provider_message_id
                )
            )
        ).scalar_one_or_none()
        return row.delivery_state if row else None


async def _reply(client: AsyncClient, inbox: dict[str, Any]) -> None:
    """Una respuesta del agente, que es lo único que puede llevar acuse."""
    conversations = (
        await client.get(
            "/messaging/conversations",
            headers=inbox["headers"],
            params={"branch_id": str(inbox["branch_id"])},
        )
    ).json()
    await client.post(
        f"/messaging/conversations/{conversations[0]['id']}/messages",
        headers=inbox["headers"],
        params={"branch_id": str(inbox["branch_id"])},
        json={"body": "Tu pedido ya salió."},
    )


async def test_a_receipt_raises_the_state(
    client: AsyncClient, inbox: dict[str, Any], fake_bridge: Any
) -> None:
    fake_bridge.next_message_id = SENT_ID
    await _reply(client, inbox)
    assert await _state_of(SENT_ID) == "sent"

    resp = await post_receipt(client, "inst-centro")

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "receipt"
    assert await _state_of(SENT_ID) == "delivered"


async def test_read_climbs_over_delivered(
    client: AsyncClient, inbox: dict[str, Any], fake_bridge: Any
) -> None:
    fake_bridge.next_message_id = SENT_ID
    await _reply(client, inbox)

    await post_receipt(client, "inst-centro", status="DELIVERY_ACK")
    await post_receipt(client, "inst-centro", status="READ")

    assert await _state_of(SENT_ID) == "read"


async def test_a_late_delivered_does_not_put_out_the_read(
    client: AsyncClient, inbox: dict[str, Any], fake_bridge: Any
) -> None:
    """El caso real: los dos acuses salen juntos y el puente los reenvía desordenados."""
    fake_bridge.next_message_id = SENT_ID
    await _reply(client, inbox)

    await post_receipt(client, "inst-centro", status="READ")
    resp = await post_receipt(client, "inst-centro", status="DELIVERY_ACK")

    assert resp.status_code == 200
    # Nada que cambiar: se reconoce como acuse y se ignora, sin tocar la fila.
    assert resp.json()["status"] == "ignored"
    assert await _state_of(SENT_ID) == "read"


async def test_a_receipt_never_enters_the_thread(
    client: AsyncClient, inbox: dict[str, Any], fake_bridge: Any
) -> None:
    """Si acabara como mensaje, el cliente parecería haber escrito `messages.update`."""
    fake_bridge.next_message_id = SENT_ID
    await _reply(client, inbox)
    thread_before = (
        await client.get(
            "/messaging/conversations",
            headers=inbox["headers"],
            params={"branch_id": str(inbox["branch_id"])},
        )
    ).json()[0]

    await post_receipt(client, "inst-centro")

    thread_after = (
        await client.get(
            "/messaging/conversations",
            headers=inbox["headers"],
            params={"branch_id": str(inbox["branch_id"])},
        )
    ).json()[0]
    assert thread_after["message_count"] == thread_before["message_count"]
    assert thread_after["status"] == thread_before["status"]


async def test_a_receipt_about_the_customers_message_does_nothing(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    """El mensaje entrante `in-1` existe y tiene ese id; aun así no lleva palomitas."""
    before = await _state_of("in-1")

    resp = await post_receipt(client, "inst-centro", key_id="in-1", from_me=False)

    assert resp.status_code == 200
    assert await _state_of("in-1") == before


async def test_a_receipt_cannot_reach_an_inbound_message_even_claiming_to_be_ours(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    """Defensa en profundidad: el `WHERE` del repositorio también exige que sea saliente.

    El filtro por `fromMe` vive en el borde; si algún día el puente mintiera o cambiara el sobre,
    esto sigue impidiendo que un acuse escriba sobre un mensaje del cliente.
    """
    before = await _state_of("in-1")

    resp = await post_receipt(client, "inst-centro", key_id="in-1", from_me=True)

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    assert await _state_of("in-1") == before


async def test_an_unknown_id_is_ignored_without_error(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    """Pasa cada vez que el dueño contesta desde su propio teléfono. Es lo normal."""
    resp = await post_receipt(client, "inst-centro", key_id="no-existe")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


async def test_an_unknown_instance_is_ignored_without_error(
    client: AsyncClient, inbox: dict[str, Any], fake_bridge: Any
) -> None:
    fake_bridge.next_message_id = SENT_ID
    await _reply(client, inbox)

    resp = await post_receipt(client, "inst-desconocida")

    assert resp.status_code == 200
    assert await _state_of(SENT_ID) == "sent"


async def test_a_receipt_with_a_bad_secret_changes_nothing(
    client: AsyncClient, inbox: dict[str, Any], fake_bridge: Any
) -> None:
    fake_bridge.next_message_id = SENT_ID
    await _reply(client, inbox)

    resp = await client.post(
        "/webhooks/whatsapp/inst-centro",
        headers={"X-Webhook-Secret": "no"},
        json={
            "event": "messages.update",
            "data": {"keyId": SENT_ID, "fromMe": True, "status": "READ"},
        },
    )

    assert resp.status_code == 401
    assert await _state_of(SENT_ID) == "sent"


async def test_a_receipt_does_not_reopen_a_closed_conversation(
    client: AsyncClient, inbox: dict[str, Any], fake_bridge: Any
) -> None:
    fake_bridge.next_message_id = SENT_ID
    await _reply(client, inbox)
    conversations = (
        await client.get(
            "/messaging/conversations",
            headers=inbox["headers"],
            params={"branch_id": str(inbox["branch_id"])},
        )
    ).json()
    await client.post(
        f"/messaging/conversations/{conversations[0]['id']}/close",
        headers=inbox["headers"],
        params={"branch_id": str(inbox["branch_id"])},
    )

    await post_receipt(client, "inst-centro", status="READ")

    async with SessionFactory() as session:
        row = (
            await session.execute(select(WhatsAppConversationModel))
        ).scalar_one()
    assert row.status == "closed"
    # Y el acuse sí se aplicó: cerrar el hilo no borra lo que pasó con el mensaje.
    assert await _state_of(SENT_ID) == "read"
