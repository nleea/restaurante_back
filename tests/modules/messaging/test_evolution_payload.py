"""Traducción del webhook de Evolution API v2 a nuestro mensaje entrante.

El sobre de Evolution es `{event, instance, data, …}` con el mensaje anidado en `data` en
formato Baileys. Nuestro parser original esperaba `{id, from, text}` planos: habría
rechazado TODOS los mensajes reales.

Y Evolution reenvía también nuestros propios envíos (`data.key.fromMe`). Sin filtrarlos,
cada respuesta que mandamos volvería a guardarse como si la hubiera escrito el cliente.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from restaurante.modules.messaging.infrastructure.api.schemas import (
    WebhookMessagePayload,
)
from tests.modules.messaging.conftest import (
    WEBHOOK_SECRET,
    create_branch,
    create_session_row,
)


def _envelope(data: dict[str, Any], event: str = "messages.upsert") -> dict[str, Any]:
    return {
        "event": event,
        "instance": "inst-centro",
        "data": data,
        "destination": "https://demo.example/webhooks/whatsapp/inst-centro",
        "date_time": "2026-07-30T10:00:00.000Z",
        "sender": "573001112233@s.whatsapp.net",
        "server_url": "https://whp.example",
        "apikey": "irrelevante",
    }


def _text_message(text: str = "Hola, ¿tienen domicilio?") -> dict[str, Any]:
    return {
        "key": {
            "remoteJid": "573001112233@s.whatsapp.net",
            "fromMe": False,
            "id": "3EB0C767D82B0A3C1F2A",
        },
        "pushName": "Ana",
        "message": {"conversation": text},
        "messageType": "conversation",
        "messageTimestamp": 1785412800,
    }


def _parse(payload: dict[str, Any]):
    return WebhookMessagePayload.model_validate(payload).to_inbound("inst-centro")


# --- Lo que sí es un mensaje -------------------------------------------------
def test_a_plain_text_message_is_translated() -> None:
    inbound = _parse(_envelope(_text_message()))

    assert inbound is not None
    assert inbound.provider_message_id == "3EB0C767D82B0A3C1F2A"
    # El JID pierde el sufijo: guardamos el número, no el identificador de WhatsApp.
    assert inbound.from_phone == "573001112233"
    assert inbound.body == "Hola, ¿tienen domicilio?"
    assert inbound.message_type == "text"
    assert inbound.sender_name == "Ana"


def test_an_extended_text_message_is_also_text() -> None:
    data = _text_message()
    data["message"] = {"extendedTextMessage": {"text": "Con una respuesta citada"}}
    data["messageType"] = "extendedTextMessage"

    inbound = _parse(_envelope(data))

    assert inbound is not None
    assert inbound.body == "Con una respuesta citada"
    assert inbound.message_type == "text"


def test_a_device_suffix_is_stripped_from_the_number() -> None:
    data = _text_message()
    data["key"]["remoteJid"] = "573001112233:12@s.whatsapp.net"

    inbound = _parse(_envelope(data))

    assert inbound is not None
    assert inbound.from_phone == "573001112233"


# --- Lo que NO debe entrar ---------------------------------------------------
def test_our_own_outgoing_messages_are_ignored() -> None:
    """El bug que esto evita: cada respuesta nuestra guardada dos veces, y como del cliente."""
    data = _text_message("Sí, claro que sí")
    data["key"]["fromMe"] = True

    assert _parse(_envelope(data)) is None


def test_other_events_are_ignored() -> None:
    """Evolution manda TODO a la misma URL: conexión, QR, presencia, contactos…"""
    for event in ("connection.update", "qrcode.updated", "contacts.upsert"):
        assert _parse(_envelope(_text_message(), event=event)) is None


def test_group_messages_are_ignored() -> None:
    """Un pedido no llega por un grupo, y responder ahí escribiría delante de terceros."""
    data = _text_message()
    data["key"]["remoteJid"] = "120363000000000000@g.us"

    assert _parse(_envelope(data)) is None


def test_a_payload_without_a_key_is_ignored() -> None:
    assert _parse(_envelope({"pushName": "Ana"})) is None


# --- Multimedia: marcador, no descarte ---------------------------------------
def test_media_becomes_a_typed_placeholder() -> None:
    cases = {
        "imageMessage": "image",
        "audioMessage": "audio",
        "locationMessage": "location",
        "documentMessage": "document",
        "stickerMessage": "sticker",
    }
    for raw_type, expected in cases.items():
        data = _text_message()
        data["message"] = {raw_type: {}}
        data["messageType"] = raw_type

        inbound = _parse(_envelope(data))

        assert inbound is not None, raw_type
        # Se guarda con su tipo para que el hilo diga QUÉ llegó, no sólo que llegó algo.
        assert inbound.message_type == expected
        assert inbound.body is None


def test_an_unknown_type_still_lands_as_unsupported() -> None:
    data = _text_message()
    data["message"] = {"pollCreationMessage": {}}
    data["messageType"] = "pollCreationMessage"

    inbound = _parse(_envelope(data))

    assert inbound is not None
    assert inbound.message_type == "unsupported"


# --- La forma plana sigue funcionando ----------------------------------------
def test_the_flat_shape_still_works() -> None:
    """Otros puentes (y nuestros tests) mandan `{id, from, text}` planos."""
    inbound = _parse({"id": "m-1", "from": "+573009998877", "text": "hola"})

    assert inbound is not None
    assert inbound.provider_message_id == "m-1"
    assert inbound.from_phone == "+573009998877"
    assert inbound.body == "hola"


# --- El webhook llega SIN subdominio de tenant --------------------------------
async def test_the_webhook_works_from_a_host_with_no_tenant_subdomain(
    client: AsyncClient,
) -> None:
    """Evolution llama desde su servidor a nuestra URL pública.

    Su Host es el de nuestro túnel/dominio, jamás `<slug>.<base_domain>`. El resto de la API
    exige ese subdominio; este endpoint no puede, y por eso resuelve el tenant desde la
    sesión que corresponde al `instance_ref` de la ruta.

    Los demás tests del webhook usan el cliente normal, cuyo Host SÍ trae tenant — así que
    pasaban sin ejercitar nunca el caso real.
    """
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")

    resp = await client.post(
        "/webhooks/whatsapp/inst-centro",
        headers={
            "X-Webhook-Secret": WEBHOOK_SECRET,
            # Un host cualquiera, como el del túnel: sin slug de tenant.
            "Host": "whp.wsquote.uk",
        },
        json=_envelope(_text_message()),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "stored"


async def test_a_tenantless_host_is_still_refused_everywhere_else(
    client: AsyncClient,
) -> None:
    """La exención es sólo para los callbacks, no una puerta abierta en toda la API."""
    resp = await client.get(
        "/messaging/sessions", headers={"Host": "whp.wsquote.uk"}
    )

    assert resp.status_code == 404
    assert "subdominio" in resp.json()["detail"].lower()


# --- JIDs `@lid`: identificador de privacidad, no teléfono ---------------------
def test_a_lid_jid_is_kept_whole_so_we_can_reply() -> None:
    """El bug real: guardábamos el `@lid` sin sufijo y las respuestas fallaban todas.

    Evolution le pega `@s.whatsapp.net` a cualquier `number` que no traiga sufijo
    (`createJid`), así que un `@lid` pelado se convertía en un usuario inexistente.
    """
    data = _text_message()
    data["key"]["remoteJid"] = "196125537607835@lid"

    inbound = _parse(_envelope(data))

    assert inbound is not None
    # Entero: es lo único con lo que se le puede responder.
    assert inbound.from_phone == "196125537607835@lid"


def test_the_real_jid_wins_over_the_lid_when_whatsapp_sends_both() -> None:
    """`remoteJidAlt` sí trae el teléfono de verdad — se prefiere siempre."""
    data = _text_message()
    data["key"]["remoteJid"] = "196125537607835@lid"
    data["key"]["remoteJidAlt"] = "573001112233@s.whatsapp.net"

    inbound = _parse(_envelope(data))

    assert inbound is not None
    assert inbound.from_phone == "573001112233"


def test_an_ordinary_jid_is_still_stripped_to_the_number() -> None:
    inbound = _parse(_envelope(_text_message()))
    assert inbound is not None
    assert inbound.from_phone == "573001112233"
