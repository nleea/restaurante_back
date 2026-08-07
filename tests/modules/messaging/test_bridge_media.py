"""El adaptador pidiéndole a Evolution el archivo de un mensaje. Sin base y sin red.

Se prueba contra un transporte falso porque lo que importa aquí es el CONTRATO con el proveedor: la
ruta, que la clave viaje entera (`{id, remoteJid, fromMe}`) y que cada forma de fallar se traduzca
a `MediaUnavailableError` — nunca a un error de envío, porque aquí no se está enviando nada.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from restaurante.modules.messaging.domain.entities import WhatsAppSession
from restaurante.modules.messaging.domain.errors import MediaUnavailableError
from restaurante.modules.messaging.infrastructure.whatsapp.bridge import (
    BridgeWhatsAppGateway,
)

SESSION = WhatsAppSession(
    id=uuid.uuid4(),
    tenant_id=uuid.uuid4(),
    branch_id=uuid.uuid4(),
    provider_instance_ref="inst-centro",
    status="connected",
    created_at=datetime.now(UTC),
    updated_at=datetime.now(UTC),
)
JID = "573001112233@s.whatsapp.net"
PHOTO = b"\xff\xd8\xff los bytes de una foto"


def _gateway(handler: Any) -> BridgeWhatsAppGateway:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return BridgeWhatsAppGateway("https://bridge.test", "apikey-1", client=client)


async def test_the_whole_message_key_is_sent() -> None:
    """El proveedor exige la clave entera; con el id suelto no devuelve nada."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["apikey"] = request.headers.get("apikey")
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"base64": base64.b64encode(PHOTO).decode()})

    data = await _gateway(handler).fetch_media(SESSION, "m-1", JID)

    assert data == PHOTO
    assert seen["url"].endswith("/chat/getBase64FromMediaMessage/inst-centro")
    # La cabecera es `apikey`, no `Bearer`.
    assert seen["apikey"] == "apikey-1"
    assert seen["json"]["message"]["key"] == {
        "id": "m-1",
        "remoteJid": JID,
        "fromMe": False,
    }


async def test_a_response_without_base64_says_what_it_probably_is() -> None:
    """La causa más probable no es la red: es que la instancia no conserva los mensajes."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"mimetype": "image/jpeg"})

    with pytest.raises(MediaUnavailableError) as excinfo:
        await _gateway(handler).fetch_media(SESSION, "m-1", JID)
    assert "no conserva los mensajes" in str(excinfo.value)


async def test_undecodable_content_is_reported_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"base64": "esto no es base64 válido!!"})

    with pytest.raises(MediaUnavailableError):
        await _gateway(handler).fetch_media(SESSION, "m-1", JID)


async def test_a_rejection_becomes_unavailable_not_a_delivery_error() -> None:
    """Traducir esto a un error de ENVÍO sería mentir sobre lo que pasó: no se mandó nada."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    with pytest.raises(MediaUnavailableError):
        await _gateway(handler).fetch_media(SESSION, "m-1", JID)


async def test_an_unreachable_bridge_becomes_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin ruta al host")

    with pytest.raises(MediaUnavailableError):
        await _gateway(handler).fetch_media(SESSION, "m-1", JID)


async def test_without_a_configured_bridge_it_says_which_setting_is_missing() -> None:
    gateway = BridgeWhatsAppGateway("")
    with pytest.raises(MediaUnavailableError) as excinfo:
        await gateway.fetch_media(SESSION, "m-1", JID)
    assert "WHATSAPP_BRIDGE_BASE_URL" in str(excinfo.value)


# --- Emparejar: a qué eventos nos suscribimos --------------------------------
async def test_pairing_subscribes_to_the_four_events_we_handle() -> None:
    """La lista de eventos ES la feature vista desde fuera.

    Sin `MESSAGES_UPDATE` no llega un solo acuse y toda la maquinaria de las palomitas está
    muerta sin que nada falle: los mensajes se quedan en "enviado" para siempre. Se prueba para
    que nadie recorte la lista más adelante "porque sobran eventos".
    """
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/webhook/set/"):
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={})
        if request.url.path.startswith("/instance/connect/"):
            return httpx.Response(200, json={"base64": "data:image/png;base64,AAA"})
        return httpx.Response(200, json={})

    await _gateway(handler).start_pairing(SESSION, "https://app.test/hook", "s3cr3t")

    events = seen["body"]["webhook"]["events"]
    assert set(events) == {
        "MESSAGES_UPSERT",
        "MESSAGES_UPDATE",
        "CONNECTION_UPDATE",
        "QRCODE_UPDATED",
    }


async def test_pairing_carries_the_secret_and_the_url() -> None:
    """El webhook queda registrado ANTES de conectar: al revés se pierden los primeros mensajes."""
    seen: dict[str, Any] = {}
    order: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        order.append(request.url.path)
        if request.url.path.startswith("/webhook/set/"):
            seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    await _gateway(handler).start_pairing(SESSION, "https://app.test/hook", "s3cr3t")

    webhook = seen["body"]["webhook"]
    assert webhook["url"] == "https://app.test/hook"
    assert webhook["headers"]["X-Webhook-Secret"] == "s3cr3t"
    assert order.index("/webhook/set/inst-centro") < order.index(
        "/instance/connect/inst-centro"
    )
