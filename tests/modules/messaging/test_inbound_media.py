"""Multimedia entrante de extremo a extremo: el orden, los gates y los fallos.

La garantía que estas pruebas defienden es una sola y es de ORDEN: **el mensaje se guarda antes de
tocar el archivo**. De ahí sale que un fallo bajando la imagen cueste la imagen y nunca el mensaje,
y es lo que un refactor descuidado invierte sin que nada más se queje.

La otra aserción que se repite es `fake_bridge.media_requests == []`: cero llamadas al puente.
Cuando aparece, está demostrando que se decidió leyendo el sobre y sin descargar nada.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.messaging.infrastructure.models import WhatsAppMessageModel
from restaurante.shared.database import SessionFactory
from tests.modules.messaging.conftest import (
    SECRET_HEADER,
    create_branch,
    create_session_row,
)

JID = "573001112233@s.whatsapp.net"


async def _post_media(
    client: AsyncClient,
    instance_ref: str,
    *,
    message_id: str,
    kind: str = "imageMessage",
    mimetype: str | None = "image/jpeg",
    file_length: int | None = 120_000,
    caption: str | None = None,
) -> Any:
    """Un `messages.upsert` de Evolution con un archivo, en formato Baileys."""
    holder: dict[str, Any] = {}
    if mimetype is not None:
        holder["mimetype"] = mimetype
    if file_length is not None:
        holder["fileLength"] = file_length
    if caption is not None:
        holder["caption"] = caption
    return await client.post(
        f"/webhooks/whatsapp/{instance_ref}",
        headers=SECRET_HEADER,
        json={
            "event": "messages.upsert",
            "instance": instance_ref,
            "data": {
                "key": {"id": message_id, "remoteJid": JID, "fromMe": False},
                "messageType": kind,
                "message": {kind: holder},
                "pushName": "Nelson",
            },
        },
    )


async def _messages() -> list[WhatsAppMessageModel]:
    async with SessionFactory() as s:
        rows = await s.execute(
            select(WhatsAppMessageModel).order_by(WhatsAppMessageModel.sent_at)
        )
        return list(rows.scalars())


async def _branch(client: AsyncClient) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")


# --- Se guarda ---------------------------------------------------------------
async def test_an_image_is_fetched_and_attached(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    await _branch(client)

    resp = await _post_media(client, "inst-centro", message_id="m-1")

    assert resp.status_code == 200, resp.text
    # Se le pidió al puente con la CLAVE del mensaje, no sólo con el id.
    assert fake_bridge.media_requests == [("m-1", JID)]
    assert media_sink.stored == [("image/jpeg", len(fake_bridge.next_media))]

    message = (await _messages())[0]
    assert message.media_type == "image"
    assert message.media_mime == "image/jpeg"
    assert message.media_url == media_sink.url
    # Y la clave del proveedor queda guardada, que es lo que permitió pedir el archivo.
    assert message.provider_remote_jid == JID


async def test_a_pdf_is_stored_like_an_image(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    """Los bancos mandan el comprobante en PDF; dejarlo fuera dejaría fuera el caso común."""
    await _branch(client)

    await _post_media(
        client,
        "inst-centro",
        message_id="m-1",
        kind="documentMessage",
        mimetype="application/pdf",
    )

    message = (await _messages())[0]
    assert message.media_type == "document"
    assert message.media_url == media_sink.url


async def test_a_caption_becomes_the_message(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    """Tirar lo que el cliente escribió es el mismo error que tirar la imagen."""
    await _branch(client)

    await _post_media(
        client,
        "inst-centro",
        message_id="m-1",
        caption="aquí va mi comprobante del pedido A3F2",
    )

    message = (await _messages())[0]
    assert message.content == "aquí va mi comprobante del pedido A3F2"
    assert message.media_url == media_sink.url


async def test_without_a_caption_the_placeholder_keeps_the_thread_readable(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    await _branch(client)
    await _post_media(client, "inst-centro", message_id="m-1")

    assert (await _messages())[0].content == "[imagen]"


# --- No se guarda, y sin gastar ----------------------------------------------
async def test_an_oversized_file_is_refused_without_calling_the_bridge(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    """La aserción es `media_requests == []`: los 20 MB no viajaron."""
    await _branch(client)

    await _post_media(
        client,
        "inst-centro",
        message_id="m-1",
        kind="videoMessage",
        mimetype="video/mp4",
        file_length=20 * 1024 * 1024,
    )

    assert fake_bridge.media_requests == []
    assert media_sink.stored == []
    message = (await _messages())[0]
    assert message.media_url is None


async def test_a_document_of_another_type_is_left_alone(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    await _branch(client)

    await _post_media(
        client,
        "inst-centro",
        message_id="m-1",
        kind="documentMessage",
        mimetype="application/vnd.ms-excel",
    )

    assert fake_bridge.media_requests == []
    message = (await _messages())[0]
    # El tipo SÍ se guarda: el hilo puede decir que llegó un documento.
    assert message.media_type == "document"
    assert message.media_url is None


async def test_a_sticker_is_not_fetched(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    """Técnicamente es un webp. Es ruido puro."""
    await _branch(client)

    await _post_media(
        client,
        "inst-centro",
        message_id="m-1",
        kind="stickerMessage",
        mimetype="image/webp",
    )

    assert fake_bridge.media_requests == []
    message = (await _messages())[0]
    assert message.media_type is None


# --- El fallo cuesta el archivo, nunca el mensaje ----------------------------
async def test_a_failing_fetch_keeps_the_message(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    """El caso que justifica el orden: el mensaje ya está guardado cuando se baja el archivo."""
    await _branch(client)
    fake_bridge.media_fails = True

    resp = await _post_media(client, "inst-centro", message_id="m-1")

    assert resp.status_code == 200, "el webhook no puede fallar por un archivo"
    message = (await _messages())[0]
    assert message.media_type == "image"
    assert message.media_url is None
    assert media_sink.stored == []


async def test_a_failing_upload_keeps_the_message(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    await _branch(client)
    media_sink.url = None  # R2 no pudo

    await _post_media(client, "inst-centro", message_id="m-1")

    message = (await _messages())[0]
    assert message.media_type == "image"
    assert message.media_url is None


# --- Idempotencia ------------------------------------------------------------
async def test_a_redelivery_does_not_fetch_or_store_twice(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    """La segunda vez no gana la inserción, así que no descarga ni sube nada."""
    await _branch(client)

    await _post_media(client, "inst-centro", message_id="m-1")
    await _post_media(client, "inst-centro", message_id="m-1")

    assert len(await _messages()) == 1
    assert len(fake_bridge.media_requests) == 1
    assert len(media_sink.stored) == 1


# --- Sin almacenamiento, el comportamiento de antes --------------------------
async def test_text_messages_are_untouched(
    client: AsyncClient, fake_bridge, media_sink
) -> None:
    """Un mensaje de texto no despierta nada de esto."""
    await _branch(client)

    await client.post(
        "/webhooks/whatsapp/inst-centro",
        headers=SECRET_HEADER,
        json={
            "event": "messages.upsert",
            "instance": "inst-centro",
            "data": {
                "key": {"id": "t-1", "remoteJid": JID, "fromMe": False},
                "messageType": "conversation",
                "message": {"conversation": "hola"},
            },
        },
    )

    assert fake_bridge.media_requests == []
    message = (await _messages())[0]
    assert message.content == "hola"
    assert message.media_type is None
