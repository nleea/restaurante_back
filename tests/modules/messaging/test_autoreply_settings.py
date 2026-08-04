"""Ajustes de respuesta automática y la acción manual de mandar la carta.

El punto de estos tests: los marcadores se validan AL GUARDAR. Descubrir a las 8pm que
`{cliente}` no existe, con un cliente esperando, no le sirve a nadie.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.messaging.infrastructure.models import (
    WhatsAppAutoreplySettingsModel,
    WhatsAppConversationModel,
    WhatsAppMessageModel,
)
from restaurante.shared.config import get_settings
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


def _payload(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "greeting_enabled": True,
        "greeting_open_text": "Hola, soy {branch_name}. Carta: {menu_link}",
        "greeting_closed_text": "Cerrados; abrimos {next_opening}. {menu_link}",
        "assistant_offer_enabled": False,
        "idle_hours": 24,
        "token_lifetime_hours": 24,
        "status_mapping": {},
    }
    base.update(over)
    return base


# --- Defaults ---------------------------------------------------------------
async def test_a_tenant_without_a_row_reads_everything_off(
    client: AsyncClient,
) -> None:
    """Instalar el change no puede cambiarle el comportamiento a nadie."""
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.get("/messaging/autoreply", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["settings"]["greeting_enabled"] is False
    assert body["settings"]["status_mapping"] == {}
    # El mapeo de fábrica SÍ viaja, para que la pantalla pueda ofrecerlo sin inventarlo.
    defaults = body["default_status_mapping"]
    assert defaults["order_received"]["enabled"] is True
    assert defaults["ready"]["enabled"] is False
    assert "menu_link" in body["greeting_placeholders"]
    assert "order_total" in body["order_placeholders"]
    # Y `{menu_link}` NO es válido en un aviso de pedido: saldría con un hueco.
    assert "menu_link" not in body["order_placeholders"]
    # Desde `assistant-core` esto ya no es "no existe para nadie": es si este DESPLIEGUE
    # puede ofrecerlo (hay credencial de proveedor y el interruptor global está en marcha).
    # La pantalla lo necesita para no dejar prometer algo que no contesta.
    settings = get_settings()
    assert body["assistant_available"] is (
        bool(settings.assistant_api_key) and not settings.assistant_kill_switch
    )


async def test_settings_round_trip(client: AsyncClient) -> None:
    await grant_only(["messaging.manage"])
    headers = await login(client)

    saved = await client.put(
        "/messaging/autoreply", headers=headers, json=_payload(idle_hours=6)
    )
    assert saved.status_code == 200, saved.text

    reread = (await client.get("/messaging/autoreply", headers=headers)).json()
    assert reread["settings"]["greeting_enabled"] is True
    assert reread["settings"]["idle_hours"] == 6


# --- Validación de marcadores -----------------------------------------------
async def test_an_unknown_placeholder_blocks_saving_and_is_named(
    client: AsyncClient,
) -> None:
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply",
        headers=headers,
        json=_payload(greeting_open_text="Hola {cliente}, mira {menu_link}"),
    )

    assert resp.status_code == 422, resp.text
    # Nombrar al culpable: "marcador inválido" a secas no arregla nada.
    assert "{cliente}" in resp.json()["detail"]


async def test_an_order_placeholder_is_rejected_in_the_greeting(
    client: AsyncClient,
) -> None:
    """`{order_total}` en el saludo no es un error de sintaxis: es un hueco garantizado."""
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply",
        headers=headers,
        json=_payload(greeting_open_text="Hola, van {order_total}"),
    )

    assert resp.status_code == 422
    assert "{order_total}" in resp.json()["detail"]


async def test_a_status_text_may_not_use_greeting_placeholders(
    client: AsyncClient,
) -> None:
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply",
        headers=headers,
        json=_payload(
            status_mapping={
                "on_the_way": {"enabled": True, "text": "Ya sale. {menu_link}"}
            }
        ),
    )

    assert resp.status_code == 422
    assert "{menu_link}" in resp.json()["detail"]


async def test_an_unknown_customer_state_is_rejected(client: AsyncClient) -> None:
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply",
        headers=headers,
        json=_payload(status_mapping={"cooking": {"enabled": True, "text": "Hola"}}),
    )

    assert resp.status_code == 422


# --- Permisos ----------------------------------------------------------------
async def test_settings_need_messaging_manage(client: AsyncClient) -> None:
    await grant_only(["messaging.read", "messaging.attend"])
    headers = await login(client)

    assert (await client.get("/messaging/autoreply", headers=headers)).status_code == 403
    assert (
        await client.put("/messaging/autoreply", headers=headers, json=_payload())
    ).status_code == 403


# --- Enlace a la carta, a mano -----------------------------------------------
async def test_an_agent_can_send_the_menu_link_by_hand(
    client: AsyncClient, fake_bridge
) -> None:
    """Existe para la conversación que ya no es `new`, y para el saludo apagado."""
    branch_id = await create_branch("centro", primary=True)
    await create_session_row(branch_id, "inst-centro")
    await create_employee(branch_id, TEST_EMAIL)
    headers = await login(client)
    await post_inbound(client, "inst-centro", message_id="in-1")

    conversations = (
        await client.get(
            "/messaging/conversations",
            headers=headers,
            params={"branch_id": str(branch_id)},
        )
    ).json()
    conversation_id = conversations[0]["id"]

    resp = await client.post(
        f"/messaging/conversations/{conversation_id}/menu-link",
        headers=headers,
        params={"branch_id": str(branch_id)},
    )

    assert resp.status_code == 201, resp.text
    link = resp.json()["link"]
    assert "/store/centro" in link
    assert "?t=" in link
    assert fake_bridge.sent[-1][1] == link
    # Queda firmado por el agente, no como mensaje del sistema: lo mandó una persona.
    async with SessionFactory() as s:
        senders = list(
            (await s.execute(select(WhatsAppMessageModel.sender_type))).scalars()
        )
    assert "employee" in senders


async def test_the_menu_link_reuses_a_live_token(
    client: AsyncClient, fake_bridge
) -> None:
    """El cliente reabre el enlace una hora después para pedir otra vez."""
    branch_id = await create_branch("centro", primary=True)
    await create_session_row(branch_id, "inst-centro")
    await create_employee(branch_id, TEST_EMAIL)
    headers = await login(client)
    await post_inbound(client, "inst-centro", message_id="in-1")
    conversation_id = (
        await client.get(
            "/messaging/conversations",
            headers=headers,
            params={"branch_id": str(branch_id)},
        )
    ).json()[0]["id"]

    first = await client.post(
        f"/messaging/conversations/{conversation_id}/menu-link",
        headers=headers,
        params={"branch_id": str(branch_id)},
    )
    second = await client.post(
        f"/messaging/conversations/{conversation_id}/menu-link",
        headers=headers,
        params={"branch_id": str(branch_id)},
    )

    assert first.json()["link"] == second.json()["link"]


async def test_sending_the_menu_link_needs_messaging_attend(
    client: AsyncClient, fake_bridge
) -> None:
    branch_id = await create_branch("centro", primary=True)
    await create_session_row(branch_id, "inst-centro")
    await create_employee(branch_id, TEST_EMAIL)
    # El webhook no lleva usuario, así que la conversación se crea sin haber entrado.
    await post_inbound(client, "inst-centro", message_id="in-1")
    async with SessionFactory() as s:
        conversation_id = (
            await s.execute(select(WhatsAppConversationModel.id))
        ).scalars().one()
    # Los permisos se recortan ANTES del primer login: el token los lleva dentro.
    await grant_only(["messaging.read"])
    headers = await login(client)

    resp = await client.post(
        f"/messaging/conversations/{conversation_id}/menu-link",
        headers=headers,
        params={"branch_id": str(branch_id)},
    )

    assert resp.status_code == 403
    assert fake_bridge.sent == []


# --- FAQs por palabra clave --------------------------------------------------
def _faq(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "faq-1",
        "name": "Ubicación",
        "enabled": True,
        "triggers": ["donde estan"],
        "text": "Estamos en {branch_address}.",
    }
    base.update(over)
    return base


async def test_the_suggested_faqs_travel_and_arrive_disabled(
    client: AsyncClient,
) -> None:
    """Instalar esto no puede encenderle cuatro respuestas automáticas a nadie."""
    await grant_only(["messaging.manage"])
    headers = await login(client)

    body = (await client.get("/messaging/autoreply", headers=headers)).json()

    # `null`, no `[]`: este tenant nunca las tocó, y esa diferencia es lo que impide que una
    # FAQ borrada resucite.
    assert body["settings"]["faqs"] is None
    suggested = body["suggested_faqs"]
    assert [f["name"] for f in suggested] == [
        "Ubicación",
        "Horario",
        "Métodos de pago",
        "Domicilios",
    ]
    assert all(f["enabled"] is False for f in suggested)
    # `pago` a secas NO es gatillo de nada: es la palabra del reclamo, no la de la pregunta.
    assert all("pago" not in f["triggers"] for f in suggested)
    assert "hours_line" in body["faq_placeholders"]
    # Y un marcador de pedido no vale en una FAQ: no hay pedido del que hablar.
    assert "order_total" not in body["faq_placeholders"]


async def test_faqs_round_trip(client: AsyncClient) -> None:
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply", headers=headers, json=_payload(faqs=[_faq()])
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["faqs"][0]["triggers"] == ["donde estan"]


async def test_an_empty_faq_list_is_saved_as_a_decision(client: AsyncClient) -> None:
    """`[]` es "ninguna" y tiene que sobrevivir a la ida y vuelta, o borrarlas no sirve."""
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply", headers=headers, json=_payload(faqs=[])
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["faqs"] == []


async def test_a_faq_text_may_not_use_order_placeholders(client: AsyncClient) -> None:
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply",
        headers=headers,
        json=_payload(faqs=[_faq(text="Tu pedido {order_number} va bien")]),
    )

    assert resp.status_code == 422
    assert "{order_number}" in resp.json()["detail"]


async def test_a_faq_without_triggers_is_rejected(client: AsyncClient) -> None:
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply", headers=headers, json=_payload(faqs=[_faq(triggers=[])])
    )

    assert resp.status_code == 422
    assert "Ubicación" in resp.json()["detail"]


async def test_duplicate_faq_ids_are_rejected(client: AsyncClient) -> None:
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply",
        headers=headers,
        json=_payload(faqs=[_faq(), _faq(name="Otra")]),
    )

    assert resp.status_code == 422


async def test_a_reserved_trigger_is_rejected(client: AsyncClient) -> None:
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply",
        headers=headers,
        json=_payload(faqs=[_faq(triggers=["asistente"])]),
    )

    assert resp.status_code == 422
    assert "asistente" in resp.json()["detail"]


async def test_a_trigger_containing_a_reserved_word_is_rejected_with_a_reason(
    client: AsyncClient,
) -> None:
    """El callejón sin salida: `cancelaciones` pasaría una validación por igualdad.

    Y luego no dispararía nunca, porque el mensaje que la activaría se va a una persona antes.
    Una FAQ encendida que no puede coincidir es peor que una rechazada: nada la explica. Por eso
    el error tiene que ENSEÑAR, no sólo prohibir.
    """
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply",
        headers=headers,
        json=_payload(
            faqs=[_faq(name="Política de cancelación", triggers=["cancelaciones"])]
        ),
    )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "cancelaciones" in detail and "cancela" in detail
    assert "una persona" in detail


# --- Respuestas rápidas ------------------------------------------------------
# Lo que se prueba aquí no es "que se guarden": es la única promesa del backend sobre las
# plantillas —que no se pueda guardar una que saldría rota— más las tres puertas de permiso.
# Cuándo se envía y a quién lo decide una persona, y eso no tiene código que probar.
def _quick(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "quick-1",
        "name": "Va en camino",
        "text": "Tu pedido ya salió.",
    }
    base.update(over)
    return base


async def test_the_suggested_quick_replies_travel(client: AsyncClient) -> None:
    await grant_only(["messaging.manage"])
    headers = await login(client)

    body = (await client.get("/messaging/autoreply", headers=headers)).json()

    # `null`, no `[]`: nunca las tocó. Es lo que impide que una plantilla borrada resucite.
    assert body["settings"]["quick_replies"] is None
    assert [q["name"] for q in body["suggested_quick_replies"]] == [
        "Va en camino",
        "Datos para pagar",
        "Gracias",
        "Un momento",
    ]
    # Sin `enabled` ni `triggers`: no dispara nada, así que no hay nada que encender ni que
    # emparejar. Si algún día reaparecen, alguien confundió esto con una FAQ.
    assert all(set(q) == {"id", "name", "text"} for q in body["suggested_quick_replies"])


async def test_quick_replies_round_trip(client: AsyncClient) -> None:
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply", headers=headers, json=_payload(quick_replies=[_quick()])
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["quick_replies"] == [_quick()]


async def test_an_empty_quick_reply_list_is_saved_as_a_decision(
    client: AsyncClient,
) -> None:
    """`[]` es "ninguna" y tiene que sobrevivir la ida y vuelta, o borrarlas no sirve."""
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply", headers=headers, json=_payload(quick_replies=[])
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["quick_replies"] == []
    # Y relerlo no las devuelve a `null`: si lo hiciera, las sugeridas volverían encima de una
    # decisión explícita del dueño.
    body = (await client.get("/messaging/autoreply", headers=headers)).json()
    assert body["settings"]["quick_replies"] == []


async def test_a_quick_reply_may_not_use_placeholders(client: AsyncClient) -> None:
    """El compositor no interpola: `{menu_link}` saldría con las llaves puestas."""
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply",
        headers=headers,
        json=_payload(quick_replies=[_quick(text="Pide aquí: {menu_link}")]),
    )

    assert resp.status_code == 422, resp.text
    assert "menu_link" in resp.text


async def test_an_invalid_save_leaves_the_stored_list_untouched(
    client: AsyncClient,
) -> None:
    """Un 422 no puede ser una forma de borrarle las plantillas a nadie."""
    await grant_only(["messaging.manage"])
    headers = await login(client)
    await client.put(
        "/messaging/autoreply", headers=headers, json=_payload(quick_replies=[_quick()])
    )

    rejected = await client.put(
        "/messaging/autoreply",
        headers=headers,
        json=_payload(quick_replies=[_quick(text="{nombre}")]),
    )

    assert rejected.status_code == 422, rejected.text
    body = (await client.get("/messaging/autoreply", headers=headers)).json()
    assert body["settings"]["quick_replies"] == [_quick()]


async def _store_quick_replies(entries: list[dict[str, Any]]) -> None:
    """Deja las plantillas guardadas sin pasar por el `PUT`, que exige `manage`.

    Hace falta porque los permisos efectivos se cachean con TTL: un test no puede pasar de
    `manage` a `attend` y que la segunda comprobación vea el cambio.
    """
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        session.add(
            WhatsAppAutoreplySettingsModel(
                tenant_id=tenant_id, quick_replies=list(entries)
            )
        )
        await session.commit()


async def test_attending_is_enough_to_read_the_quick_replies(
    client: AsyncClient,
) -> None:
    """Quien atiende el chat en hora punta no administra nada. Por eso el endpoint aparte."""
    await _store_quick_replies([_quick()])
    await grant_only(["messaging.attend"])
    headers = await login(client)

    resp = await client.get("/messaging/quick-replies", headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"quick_replies": [_quick()]}


async def test_attending_is_not_enough_to_save_the_quick_replies(
    client: AsyncClient,
) -> None:
    await grant_only(["messaging.attend"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply", headers=headers, json=_payload(quick_replies=[_quick()])
    )

    assert resp.status_code == 403, resp.text


async def test_reading_the_inbox_is_not_enough_to_see_the_quick_replies(
    client: AsyncClient,
) -> None:
    """La lista sólo existe para meterla en una respuesta: quien no responde no la necesita."""
    await grant_only(["messaging.read"])
    headers = await login(client)

    resp = await client.get("/messaging/quick-replies", headers=headers)

    assert resp.status_code == 403, resp.text


async def test_the_inbox_never_receives_the_suggested_quick_replies(
    client: AsyncClient,
) -> None:
    """Enseñarle al mesero plantillas que el dueño no aprobó es hablar por el negocio."""
    await grant_only(["messaging.attend"])
    headers = await login(client)

    resp = await client.get("/messaging/quick-replies", headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"quick_replies": []}


async def test_reading_the_quick_replies_emits_nothing(client: AsyncClient) -> None:
    """La lista es inerte: leerla no manda mensajes ni mueve ninguna conversación."""
    await grant_only(["messaging.attend"])
    headers = await login(client)

    await client.get("/messaging/quick-replies", headers=headers)

    async with SessionFactory() as session:
        messages = (await session.execute(select(WhatsAppMessageModel))).scalars().all()
        conversations = (
            (await session.execute(select(WhatsAppConversationModel))).scalars().all()
        )
    assert messages == []
    assert conversations == []
