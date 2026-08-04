"""Mandar un archivo por el chat.

Dos afirmaciones sostienen el fichero, y las dos son sobre no perder ni prometer de más:

- **La invariante de salida vale igual para un archivo.** Un PDF no solicitado hace que baneen un
  número tan bien como un texto no solicitado, o mejor.
- **Se persiste antes de transmitir.** Un archivo que se traga un puente caído sigue en el hilo
  marcado como fallido; si no, el agente cree que lo mandó.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.messaging.infrastructure.models import WhatsAppMessageModel
from restaurante.shared.database import SessionFactory
from tests.conftest import TEST_EMAIL
from tests.modules.messaging.conftest import (
    create_branch,
    create_employee,
    create_session_row,
    grant_only,
    login,
    post_inbound,
)

PHONE = "+573001112233"
PNG = b"\x89PNG\r\n\x1a\n una imagen"


async def _outbound() -> list[WhatsAppMessageModel]:
    async with SessionFactory() as s:
        rows = await s.execute(
            select(WhatsAppMessageModel)
            .where(WhatsAppMessageModel.sender_type == "employee")
            .order_by(WhatsAppMessageModel.sent_at)
        )
        return list(rows.scalars())


async def _conversation_id() -> str:
    from restaurante.modules.messaging.infrastructure.models import (
        WhatsAppConversationModel,
    )

    async with SessionFactory() as s:
        row = (await s.execute(select(WhatsAppConversationModel))).scalars().first()
        return str(row.id)


async def _wired(client: AsyncClient) -> tuple[str, str]:
    """Sede emparejada, un empleado, y un cliente que YA escribió."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await create_employee(branch, TEST_EMAIL)
    await post_inbound(client, "inst-centro", message_id="in-1", phone=PHONE)
    await grant_only(["messaging.read", "messaging.attend"])
    return str(branch), await _conversation_id()


async def _send(
    client: AsyncClient,
    branch: str,
    conversation: str,
    headers: dict[str, str],
    *,
    content: bytes = PNG,
    content_type: str = "image/png",
    caption: str = "",
):
    return await client.post(
        f"/messaging/conversations/{conversation}/media",
        params={"branch_id": branch},
        headers=headers,
        files={"file": ("comprobante.png", content, content_type)},
        data={"caption": caption},
    )


async def test_a_file_is_sent_stored_and_left_in_the_thread(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    branch, conversation = await _wired(client)
    headers = await login(client)

    resp = await _send(client, branch, conversation, headers, caption="Aquí tienes")

    assert resp.status_code == 201, resp.text
    sent = await _outbound()
    assert len(sent) == 1
    assert sent[0].media_type == "image"
    assert sent[0].media_mime == "image/png"
    # Guardado en R2, para que el agente vea mañana lo que mandó hoy.
    assert sent[0].media_url == media_sink.url
    # El pie es el texto del mensaje, igual que en los entrantes.
    assert sent[0].content == "Aquí tienes"
    assert sent[0].delivery_state == "sent"
    # Y salió de verdad por el puente, al teléfono NORMALIZADO (así se guarda el contacto).
    assert fake_bridge.media_sent[0][0] == "573001112233"
    assert fake_bridge.media_sent[0][1] == "image/png"


async def test_a_pdf_goes_out_as_a_document(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    branch, conversation = await _wired(client)
    headers = await login(client)

    await _send(
        client,
        branch,
        conversation,
        headers,
        content=b"%PDF-1.4",
        content_type="application/pdf",
    )

    assert (await _outbound())[0].media_type == "document"


async def test_a_failed_send_keeps_the_file_in_the_thread(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    """Es la razón de persistir antes de transmitir."""
    branch, conversation = await _wired(client)
    headers = await login(client)
    fake_bridge.fail = True

    resp = await _send(client, branch, conversation, headers)

    assert resp.status_code == 502, resp.text
    sent = await _outbound()
    assert len(sent) == 1
    assert sent[0].delivery_state == "failed"
    # Y con su URL: el agente ve QUÉ intentó mandar, no un hueco.
    assert sent[0].media_url == media_sink.url


async def test_an_unsupported_type_is_refused_before_anything_happens(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    branch, conversation = await _wired(client)
    headers = await login(client)

    resp = await _send(
        client,
        branch,
        conversation,
        headers,
        content=b"MZ",
        content_type="application/x-msdownload",
    )

    assert resp.status_code == 422
    assert await _outbound() == []
    assert fake_bridge.media_sent == []


async def test_an_oversized_file_is_refused(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    branch, conversation = await _wired(client)
    headers = await login(client)

    resp = await _send(client, branch, conversation, headers, content=b"x" * (5 * 1024 * 1024 + 1))

    assert resp.status_code == 422
    assert fake_bridge.media_sent == []


async def test_sending_needs_the_attend_permission(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    branch, conversation = await _wired(client)
    await grant_only(["messaging.read"])
    headers = await login(client)

    resp = await _send(client, branch, conversation, headers)

    assert resp.status_code == 403
    assert fake_bridge.media_sent == []
