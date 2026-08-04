"""El saludo automático: incondicional, una sola vez, y consciente de la sede.

Cero LLM. Lo que decide qué se dice son los horarios de la sucursal y unos ajustes por
tenant — nada de detectar intención.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from restaurante.modules.business.infrastructure.models import OperatingHoursModel
from restaurante.modules.messaging.infrastructure.models import (
    WhatsAppAutoreplySettingsModel,
    WhatsAppConversationModel,
    WhatsAppMessageModel,
)
from restaurante.shared.database import SessionFactory
from tests.modules.messaging.conftest import (
    create_branch,
    create_session_row,
    demo_tenant_id,
    post_inbound,
)


async def _enable_greeting(**over: object) -> None:
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        row = (
            await s.execute(
                select(WhatsAppAutoreplySettingsModel).where(
                    WhatsAppAutoreplySettingsModel.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = WhatsAppAutoreplySettingsModel(tenant_id=tenant_id)
            s.add(row)
        row.greeting_enabled = True
        for key, value in over.items():
            setattr(row, key, value)
        await s.commit()


async def _open_all_week(branch_id: uuid.UUID) -> None:
    """Abierto 24/7, para que el saludo sea siempre el de 'abierto'."""
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        for weekday in range(7):
            s.add(
                OperatingHoursModel(
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    weekday=weekday,
                    open_minute=0,
                    close_minute=1439,
                )
            )
        await s.commit()


async def _closed_all_week_except(branch_id: uuid.UUID, weekday: int) -> None:
    """Una sola ventana, para forzar el saludo de 'cerrado' con próxima apertura real."""
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        s.add(
            OperatingHoursModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                weekday=weekday,
                open_minute=8 * 60,
                close_minute=9 * 60,
            )
        )
        await s.commit()


async def _system_messages() -> list[WhatsAppMessageModel]:
    async with SessionFactory() as s:
        rows = await s.execute(
            select(WhatsAppMessageModel)
            .where(WhatsAppMessageModel.sender_type == "system")
            .order_by(WhatsAppMessageModel.sent_at)
        )
        return list(rows.scalars())


async def _conversation_statuses() -> list[str]:
    async with SessionFactory() as s:
        return list(
            (await s.execute(select(WhatsAppConversationModel.status))).scalars()
        )


# --- Sale una vez ------------------------------------------------------------
async def test_greets_once_on_a_new_conversation(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _enable_greeting()

    await post_inbound(client, "inst-centro", message_id="g-1")

    assert len(fake_bridge.sent) == 1
    # Queda en el hilo como mensaje del sistema: el agente ve lo que se dijo en su nombre.
    assert len(await _system_messages()) == 1
    assert await _conversation_statuses() == ["greeted"]


async def test_further_messages_do_not_re_greet(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _enable_greeting()

    await post_inbound(client, "inst-centro", message_id="g-1")
    await post_inbound(client, "inst-centro", message_id="g-2")
    await post_inbound(client, "inst-centro", message_id="g-3")

    # Tres mensajes del cliente, UN saludo.
    assert len(fake_bridge.sent) == 1


async def test_greeting_is_unconditional_including_media(
    client: AsyncClient, fake_bridge
) -> None:
    """"quiero pedir", "buenas" y una foto merecen la misma primera respuesta."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _enable_greeting()

    await post_inbound(
        client, "inst-centro", message_id="g-1", text=None, message_type="image"
    )

    assert len(fake_bridge.sent) == 1


async def test_a_new_conversation_after_the_idle_window_is_greeted_again(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _enable_greeting()
    await post_inbound(client, "inst-centro", message_id="g-1")

    # Envejecer la conversación más allá de la ventana: la siguiente es OTRA conversación.
    stale = datetime.now(UTC) - timedelta(hours=30)
    async with SessionFactory() as s:
        await s.execute(update(WhatsAppMessageModel).values(sent_at=stale))
        await s.execute(update(WhatsAppConversationModel).values(started_at=stale))
        await s.commit()

    await post_inbound(client, "inst-centro", message_id="g-2")

    # Dos conversaciones, dos saludos. Es el precio de cerrar por inactividad.
    assert len(fake_bridge.sent) == 2


# --- Apagado -----------------------------------------------------------------
async def test_disabled_greeting_sends_nothing_and_leaves_it_new(
    client: AsyncClient, fake_bridge
) -> None:
    """Instalar el change no puede cambiarle el comportamiento a nadie."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    # sin _enable_greeting()

    await post_inbound(client, "inst-centro", message_id="g-1")

    assert fake_bridge.sent == []
    # `new`, no `greeted`: no se marca como saludado algo que nadie saludó.
    assert await _conversation_statuses() == ["new"]


# --- Abierto / cerrado -------------------------------------------------------
async def test_an_open_branch_gets_the_link(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _enable_greeting()

    await post_inbound(client, "inst-centro", message_id="g-1")

    _phone, text = fake_bridge.sent[0]
    assert "/store/centro" in text
    assert "?t=" in text  # el token viaja en el enlace
    assert "cerrados" not in text


async def test_a_closed_branch_states_the_real_next_opening(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    # Ventana de una hora en un día concreto → casi siempre cerrado.
    tomorrow = (datetime.now(UTC).weekday() + 1) % 7
    await _closed_all_week_except(branch, tomorrow)
    await _enable_greeting()

    await post_inbound(client, "inst-centro", message_id="g-1")

    _phone, text = fake_bridge.sent[0]
    assert "cerrados" in text
    # La hora sale de los horarios reales, no de un texto fijo.
    assert "8:00" in text
    # Y el enlace sigue estando: puede ir mirando la carta.
    assert "/store/centro" in text


async def test_two_branches_get_their_own_link_from_one_tenant_text(
    client: AsyncClient, fake_bridge
) -> None:
    """El texto es de tenant; la sede aporta su nombre, su enlace y sus horarios."""
    centro = await create_branch("centro", primary=True)
    norte = await create_branch("norte")
    await create_session_row(centro, "inst-centro")
    await create_session_row(norte, "inst-norte")
    await _open_all_week(centro)
    await _open_all_week(norte)
    await _enable_greeting()

    await post_inbound(client, "inst-centro", message_id="g-1", phone="+573001112233")
    await post_inbound(client, "inst-norte", message_id="g-2", phone="+573009998877")

    links = [text for _phone, text in fake_bridge.sent]
    assert any("/store/centro" in t for t in links)
    assert any("/store/norte" in t for t in links)


# --- Oferta del asistente ----------------------------------------------------
async def test_the_assistant_offer_is_absent_without_entitlement(
    client: AsyncClient, fake_bridge
) -> None:
    """El saludo nunca debe ofrecer algo que no vaya a responder."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _enable_greeting(assistant_offer_enabled=False)

    await post_inbound(client, "inst-centro", message_id="g-1")

    _phone, text = fake_bridge.sent[0]
    assert "asistente" not in text.lower()


async def test_the_assistant_offer_appears_with_entitlement(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _enable_greeting(assistant_offer_enabled=True)

    await post_inbound(client, "inst-centro", message_id="g-1")

    _phone, text = fake_bridge.sent[0]
    assert "asistente" in text.lower()


async def test_the_assistant_offer_never_goes_out_with_the_business_closed(
    client: AsyncClient, fake_bridge
) -> None:
    """Cerrado no se ofrece: fuera de horario el asistente tampoco contesta.

    Es la misma regla que la falta de derecho —no prometer lo que no se va a atender—, pero
    por la otra vía: el asistente EXISTE y está encendido, y a esta hora está apagado por
    horario. Un "escribe 1" a las once de la noche no lo contesta ni el bot ni una persona.
    """
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    tomorrow = (datetime.now(UTC).weekday() + 1) % 7
    await _closed_all_week_except(branch, tomorrow)
    await _enable_greeting(assistant_offer_enabled=True)

    await post_inbound(client, "inst-centro", message_id="g-1")

    _phone, text = fake_bridge.sent[0]
    assert "cerrados" in text
    assert "asistente" not in text.lower()
    assert "*1*" not in text


# --- Texto propio ------------------------------------------------------------
async def test_a_custom_text_is_rendered_with_the_branch_values(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _enable_greeting(
        greeting_open_text="Bienvenido a {branch_name}. Pide en {menu_link}"
    )

    await post_inbound(client, "inst-centro", message_id="g-1")

    _phone, text = fake_bridge.sent[0]
    assert text.startswith("Bienvenido a Sede centro. Pide en http")


# --- El saludo nunca cuesta el mensaje ---------------------------------------
async def test_a_failing_greeting_never_loses_the_inbound_message(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _enable_greeting()
    fake_bridge.fail = True  # el puente rechaza el envío

    resp = await post_inbound(client, "inst-centro", message_id="g-1")

    assert resp.status_code == 200
    assert resp.json()["status"] == "stored"
    # El mensaje del cliente está guardado; lo que se perdió es el saludo.
    async with SessionFactory() as s:
        inbound = list(
            (
                await s.execute(
                    select(WhatsAppMessageModel).where(
                        WhatsAppMessageModel.sender_type == "contact"
                    )
                )
            ).scalars()
        )
    assert len(inbound) == 1


async def test_without_a_public_storefront_url_it_says_nothing(
    client: AsyncClient, fake_bridge, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un enlace relativo por WhatsApp no es clicable. Mejor callar que mandar basura."""
    from restaurante.shared.config import get_settings

    monkeypatch.setattr(get_settings(), "storefront_base_url", "", raising=False)
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _enable_greeting()

    resp = await post_inbound(client, "inst-centro", message_id="g-1")

    assert resp.status_code == 200
    assert fake_bridge.sent == []
    # Sigue `new`: no se marca saludado lo que no se saludó, así que al configurarlo
    # el próximo mensaje sí saluda.
    assert await _conversation_statuses() == ["new"]


async def test_the_link_carries_the_tenant_subdomain(
    client: AsyncClient, fake_bridge
) -> None:
    """El enlace es un dato POR TENANT.

    El front deduce a qué API hablar del subdominio del navegador. Una URL global mandaría
    a los clientes de un negocio a la carta de otro — o a ninguna.
    """
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _enable_greeting()

    await post_inbound(client, "inst-centro", message_id="g-1")

    _phone, text = fake_bridge.sent[0]
    # El slug del tenant va como subdominio, no en la ruta.
    assert "https://demo.example.test/store/centro?t=" in text
