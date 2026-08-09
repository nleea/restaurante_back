"""El adaptador publicando un estado en Evolution. Sin base y sin red.

Se prueba contra un transporte falso porque lo que importa es el CONTRATO con el proveedor, y ese
contrato tiene tres exigencias que no son negociables (leídas de `formatStatusMessage`):

- un estado de texto sin `backgroundColor` y sin `font` es un 400,
- `statusJidList` es obligatorio si no se manda `allContacts`,
- y `allContacts` **nunca** se manda: es la tabla de contactos de Evolution, sobre la que ni el
  opt-out ni la ventana de inactividad tienen efecto.

La última prueba del fichero es la incómoda: el puente acepta con 201 aunque se le haya caído la
mitad de las tandas, así que "publicado" es lo máximo que este adaptador puede afirmar.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from restaurante.modules.messaging.domain.entities import WhatsAppSession
from restaurante.modules.messaging.domain.errors import MessageDeliveryError
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
JIDS = ["573001112233@s.whatsapp.net", "573002223344@s.whatsapp.net"]


def _gateway(handler: Any) -> BridgeWhatsAppGateway:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return BridgeWhatsAppGateway("https://bridge.test", "apikey-1", client=client)


def _capture(seen: dict[str, Any], *, body: Any = None, status: int = 201) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["apikey"] = request.headers.get("apikey")
        seen["payload"] = json.loads(request.content.decode())
        return httpx.Response(status, json=body if body is not None else {"id": "st-1"})

    return handler


async def test_a_text_status_carries_the_two_fields_the_provider_demands() -> None:
    """Sin `backgroundColor` y `font` el proveedor devuelve 400. Van siempre."""
    seen: dict[str, Any] = {}
    gateway = _gateway(_capture(seen))

    result = await gateway.publish_status(
        SESSION,
        JIDS,
        status_type="text",
        content="Hoy hay sancocho",
        bg_color="#0B3D2E",
        font=2,
    )

    assert result == "st-1"
    assert seen["url"] == "https://bridge.test/message/sendStatus/inst-centro"
    assert seen["apikey"] == "apikey-1"
    assert seen["payload"] == {
        "type": "text",
        "content": "Hoy hay sancocho",
        "statusJidList": JIDS,
        "backgroundColor": "#0B3D2E",
        "font": 2,
    }


async def test_all_contacts_is_never_sent() -> None:
    """El botón que quema el número: lee la tabla de Evolution, no la nuestra.

    Sobre esa tabla no tienen ningún efecto ni el opt-out, ni la ventana de 90 días, ni el tope.
    """
    seen: dict[str, Any] = {}
    gateway = _gateway(_capture(seen))

    await gateway.publish_status(
        SESSION, JIDS, status_type="text", content="x", bg_color="#000", font=1
    )

    assert "allContacts" not in seen["payload"]
    assert seen["payload"]["statusJidList"] == JIDS


async def test_an_image_status_travels_as_a_url_with_its_caption() -> None:
    """URL y no base64, al contrario que `send_media`: el archivo ya está en R2 con una URL."""
    seen: dict[str, Any] = {}
    gateway = _gateway(_capture(seen))

    await gateway.publish_status(
        SESSION,
        JIDS,
        status_type="image",
        content="https://cdn.test/abc.jpg",
        caption="Menú del día",
    )

    assert seen["payload"]["type"] == "image"
    assert seen["payload"]["content"] == "https://cdn.test/abc.jpg"
    assert seen["payload"]["caption"] == "Menú del día"
    # Una imagen no lleva los campos de la tarjeta de texto.
    assert "backgroundColor" not in seen["payload"]
    assert "font" not in seen["payload"]


async def test_a_rejection_becomes_a_delivery_error() -> None:
    seen: dict[str, Any] = {}
    gateway = _gateway(_capture(seen, status=400, body={"message": "Font is required"}))

    with pytest.raises(MessageDeliveryError):
        await gateway.publish_status(
            SESSION, JIDS, status_type="text", content="x", bg_color="#000", font=1
        )


async def test_an_unreachable_bridge_becomes_a_delivery_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    with pytest.raises(MessageDeliveryError):
        await _gateway(handler).publish_status(
            SESSION, JIDS, status_type="text", content="x", bg_color="#000", font=1
        )


async def test_an_unconfigured_bridge_says_so_instead_of_failing_obscurely() -> None:
    """Mal configurado y no contactable son dos cosas distintas, y se dicen distintas."""
    gateway = BridgeWhatsAppGateway("", "")

    with pytest.raises(MessageDeliveryError, match="no está configurado"):
        await gateway.publish_status(
            SESSION, JIDS, status_type="text", content="x", bg_color="#000", font=1
        )


async def test_publishing_to_nobody_is_refused() -> None:
    """No es un caso a soportar: es una llamada que sobra, y quien llama ya sabe si está vacía."""
    seen: dict[str, Any] = {}
    gateway = _gateway(_capture(seen))

    with pytest.raises(MessageDeliveryError):
        await gateway.publish_status(
            SESSION, [], status_type="text", content="x", bg_color="#000", font=1
        )
    assert "payload" not in seen  # no salió ninguna petición


async def test_an_accepted_status_without_an_id_returns_none_instead_of_empty() -> None:
    """"No lo sabemos" y "es la cadena vacía" son distintos, y la columna es nullable para decirlo.

    El id de un estado sirve para correlacionar, no para reconciliar: un estado no tiene acuses que
    emparejar, así que no tenerlo no es un fallo.
    """
    seen: dict[str, Any] = {}
    gateway = _gateway(_capture(seen, body={"ok": True}))

    assert (
        await gateway.publish_status(
            SESSION, JIDS, status_type="text", content="x", bg_color="#000", font=1
        )
        is None
    )


async def test_a_partial_batch_failure_still_looks_like_success() -> None:
    """La prueba incómoda, y está aquí para que quede constancia de la limitación.

    El puente parte en tandas de diez y las reenvía dentro de un `Promise.allSettled`: si la tanda 7
    de 20 se cae, se la come y devuelve 201 con el mensaje de la PRIMERA. Desde este lado es
    indistinguible de un éxito completo.

    Por eso el vocabulario del módulo es "publicado" y "enviado a N", nunca "entregado" ni "visto
    por": el adaptador no puede afirmar más que esto, y ninguna capa de arriba puede inventarlo.
    """
    seen: dict[str, Any] = {}
    gateway = _gateway(_capture(seen, body={"key": {"id": "st-first-batch"}}))

    result = await gateway.publish_status(
        SESSION,
        [f"5730{i:08d}@s.whatsapp.net" for i in range(200)],
        status_type="text",
        content="x",
        bg_color="#000",
        font=1,
    )

    # Lo único que se sabe: el puente aceptó, y este es el id de la primera tanda.
    assert result == "st-first-batch"
    assert len(seen["payload"]["statusJidList"]) == 200
