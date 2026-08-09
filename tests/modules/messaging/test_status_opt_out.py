"""El opt-out de estados, desde el hilo donde el cliente lo pidió.

La propiedad que hace defendible esta feature es lo que el opt-out **no** hace: no cambia el estado
de la conversación, no la saca de la bandeja y no impide responderle. Es lo que lo separa de borrar
el contacto, que era la única forma de sacar a alguien de la lista antes de que existiera la columna
— y se llevaba su historial por delante.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.messaging.infrastructure.models import (
    WhatsAppConversationModel,
)
from restaurante.shared.database import SessionFactory

from .conftest import grant_only, login, post_inbound


async def _thread(client: AsyncClient, inbox: dict[str, Any]) -> dict[str, Any]:
    conversations = (
        await client.get(
            "/messaging/conversations",
            params={"branch_id": str(inbox["branch_id"])},
            headers=inbox["headers"],
        )
    ).json()
    response = await client.get(
        f"/messaging/conversations/{conversations[0]['id']}",
        params={"branch_id": str(inbox["branch_id"])},
        headers=inbox["headers"],
    )
    assert response.status_code == 200
    return response.json()


async def _set_opt_out(
    client: AsyncClient, inbox: dict[str, Any], conversation_id: str, value: bool
) -> Any:
    return await client.put(
        f"/messaging/conversations/{conversation_id}/status-opt-out",
        params={"branch_id": str(inbox["branch_id"])},
        headers=inbox["headers"],
        json={"opted_out": value},
    )


@pytest.mark.asyncio
async def test_a_contact_starts_not_opted_out(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    """Nadie estrena comportamiento: la columna nace `false` para todos."""
    thread = await _thread(client, inbox)
    assert thread["contact_status_opt_out"] is False


@pytest.mark.asyncio
async def test_the_attendant_can_mark_it_where_they_read_it(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    thread = await _thread(client, inbox)
    response = await _set_opt_out(client, inbox, thread["id"], True)

    assert response.status_code == 200
    assert response.json()["contact_status_opt_out"] is True


@pytest.mark.asyncio
async def test_it_can_be_undone(client: AsyncClient, inbox: dict[str, Any]) -> None:
    thread = await _thread(client, inbox)
    await _set_opt_out(client, inbox, thread["id"], True)
    response = await _set_opt_out(client, inbox, thread["id"], False)

    assert response.json()["contact_status_opt_out"] is False


@pytest.mark.asyncio
async def test_marking_does_not_touch_the_conversation(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    """Ni el estado, ni el titular, ni los mensajes. Es una marca del contacto, no del hilo."""
    before = await _thread(client, inbox)
    await _set_opt_out(client, inbox, before["id"], True)
    after = await _thread(client, inbox)

    assert after["status"] == before["status"]
    assert after["employee_id"] == before["employee_id"]
    assert after["closed_at"] == before["closed_at"]
    assert len(after["messages"]) == len(before["messages"])


@pytest.mark.asyncio
async def test_the_thread_stays_in_the_inbox(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    thread = await _thread(client, inbox)
    await _set_opt_out(client, inbox, thread["id"], True)

    conversations = (
        await client.get(
            "/messaging/conversations",
            params={"branch_id": str(inbox["branch_id"])},
            headers=inbox["headers"],
        )
    ).json()
    assert [c["id"] for c in conversations] == [thread["id"]]


@pytest.mark.asyncio
async def test_replying_still_works(
    client: AsyncClient, inbox: dict[str, Any], fake_bridge: Any
) -> None:
    """Un contacto marcado sigue siendo alcanzable para RESPONDERLE.

    El opt-out es de estados, no del canal. Si esto se cae, la marca se ha convertido en un bloqueo
    y una petición razonable ("no me manden promociones") habría cortado la atención.
    """
    thread = await _thread(client, inbox)
    await _set_opt_out(client, inbox, thread["id"], True)
    await client.post(
        f"/messaging/conversations/{thread['id']}/claim",
        params={"branch_id": str(inbox["branch_id"])},
        headers=inbox["headers"],
    )

    response = await client.post(
        f"/messaging/conversations/{thread['id']}/messages",
        params={"branch_id": str(inbox["branch_id"])},
        headers=inbox["headers"],
        json={"body": "Listo, no le mandamos más"},
    )

    assert response.status_code == 201
    assert response.json()["contact_status_opt_out"] is True


@pytest.mark.asyncio
async def test_a_second_inbound_does_not_undo_the_mark(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    """Escribir otra vez no es retirar la petición."""
    thread = await _thread(client, inbox)
    await _set_opt_out(client, inbox, thread["id"], True)
    await post_inbound(client, "inst-centro", message_id="in-2")

    assert (await _thread(client, inbox))["contact_status_opt_out"] is True


@pytest.mark.asyncio
async def test_attend_is_the_permission_that_gates_it(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    """`attend` y no `manage`: lo usa quien lee los chats, no quien configura las publicaciones.

    El id de la conversación se lee de la BASE y no por el API a propósito: los permisos efectivos
    se cachean con TTL (`RbacPermissionCache`), así que una petición autenticada ANTES del
    `grant_only` deja cacheados los del admin y el 403 no llega nunca. Es el motivo de que todas las
    pruebas de permisos de este módulo llamen a `grant_only` antes de tocar el API.
    """
    async with SessionFactory() as session:
        conversation_id = (
            await session.execute(select(WhatsAppConversationModel.id))
        ).scalar_one()

    await grant_only(["messaging.read"])
    inbox["headers"] = await login(client)

    response = await _set_opt_out(client, inbox, str(conversation_id), True)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_an_unknown_conversation_is_a_404(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    response = await _set_opt_out(
        client, inbox, "11111111-1111-1111-1111-111111111111", True
    )
    assert response.status_code == 404
