"""El estado de la sesión se entera de que el número está conectado.

Existe por un fallo reportado desde producción: el número estaba vinculado y recibiendo
mensajes desde hacía días, y la base de datos seguía diciendo `qr_pending`. El único camino
que existía para cambiarlo era que una persona llamara al endpoint de estado a mano.

Las consecuencias eran tres, y ninguna se veía como lo que era:

- la pantalla de Números decía "Esperando escaneo del QR" para siempre,
- el escalado de alertas se negaba a salir ("la sucursal no tiene número conectado"),
- y la regla `whatsapp_session_down` habría avisado en falso sobre una sucursal sana.

Se arregla por dos caminos, como el resto del sistema: el evento del puente da la latencia y
puede perderse; recibir un mensaje es la garantía y no puede.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.messaging.infrastructure.models import WhatsAppSessionModel
from restaurante.shared.database import SessionFactory
from tests.modules.messaging.conftest import (
    SECRET_HEADER,
    create_branch,
    create_session_row,
    post_inbound,
)

pytestmark = pytest.mark.asyncio


async def _status(session_id: uuid.UUID) -> tuple[str, str | None]:
    async with SessionFactory() as s:
        row = await s.get(WhatsAppSessionModel, session_id)
        assert row is not None
        return row.status, row.phone_number


async def _post_event(
    client: AsyncClient, instance_ref: str, data: dict[str, Any]
) -> Any:
    return await client.post(
        f"/webhooks/whatsapp/{instance_ref}",
        headers=SECRET_HEADER,
        json={"event": "connection.update", "instance": instance_ref, "data": data},
    )


# --- El evento del puente (la latencia) --------------------------------------
async def test_connecting_marks_the_session_connected(client: AsyncClient) -> None:
    branch = await create_branch("centro", primary=True)
    session_id = await create_session_row(branch, "inst-1", status="qr_pending")

    resp = await _post_event(client, "inst-1", {"state": "open"})

    assert resp.status_code == 200, resp.text
    status, _ = await _status(session_id)
    assert status == "connected"


async def test_the_phone_number_arrives_with_the_connection(
    client: AsyncClient,
) -> None:
    """Al vincular sólo se sabe la referencia de instancia; el número llega al conectar."""
    branch = await create_branch("centro", primary=True)
    session_id = await create_session_row(branch, "inst-1", status="qr_pending")

    await _post_event(
        client, "inst-1", {"state": "open", "wuid": "573001112233@s.whatsapp.net"}
    )

    _, phone = await _status(session_id)
    assert phone == "573001112233"


async def test_a_dropped_connection_is_recorded(client: AsyncClient) -> None:
    branch = await create_branch("centro", primary=True)
    session_id = await create_session_row(branch, "inst-1")

    await _post_event(client, "inst-1", {"state": "close"})

    # Y ESTO es lo que la regla de "el WhatsApp dejó de recibir" necesita para ser cierta.
    status, _ = await _status(session_id)
    assert status == "disconnected"


async def test_an_unknown_state_changes_nothing(client: AsyncClient) -> None:
    branch = await create_branch("centro", primary=True)
    session_id = await create_session_row(branch, "inst-1")

    resp = await _post_event(client, "inst-1", {"state": "algo-nuevo"})

    # Un estado que no conocemos no puede declarar la sucursal muda por su cuenta.
    assert resp.status_code == 200
    status, _ = await _status(session_id)
    assert status == "connected"


async def test_an_event_for_an_unknown_instance_is_acknowledged(
    client: AsyncClient,
) -> None:
    # 200 igual: un 4xx haría que el puente reintentara para siempre.
    resp = await _post_event(client, "no-existe", {"state": "open"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


# --- El mensaje entrante (la garantía) ---------------------------------------
async def test_receiving_a_message_proves_the_session_is_connected(
    client: AsyncClient, fake_bridge
) -> None:
    """La red de seguridad.

    Si el evento de conexión se perdió —Evolution reinició antes de que existiera el
    webhook, un despliegue viejo, lo que sea—, el primer mensaje que entre lo corrige. No se
    puede perder, porque llega por el mismo camino que el mensaje.
    """
    branch = await create_branch("centro", primary=True)
    session_id = await create_session_row(branch, "inst-1", status="qr_pending")

    await post_inbound(client, "inst-1", message_id="m-1")

    status, _ = await _status(session_id)
    assert status == "connected"


async def test_a_message_on_a_session_believed_disconnected_also_fixes_it(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await create_branch("centro", primary=True)
    session_id = await create_session_row(branch, "inst-1", status="disconnected")

    await post_inbound(client, "inst-1", message_id="m-1")

    status, _ = await _status(session_id)
    assert status == "connected"


async def test_the_message_is_still_stored(client: AsyncClient, fake_bridge) -> None:
    """Corregir el estado no puede costar el mensaje que lo demostró."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-1", status="qr_pending")

    resp = await post_inbound(client, "inst-1", message_id="m-1")

    assert resp.status_code == 200, resp.text
    async with SessionFactory() as s:
        from restaurante.modules.messaging.infrastructure.models import (
            WhatsAppMessageModel,
        )

        rows = (await s.execute(select(WhatsAppMessageModel.id))).scalars().all()
    assert len(rows) >= 1
