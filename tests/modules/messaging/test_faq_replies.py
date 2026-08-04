"""Las FAQs contestando de verdad: los dos gates, el estado y la emisión única.

`test_faq_matching.py` prueba que el motor distingue una pregunta de un reclamo. Aquí se prueba
lo otro, que es lo que hace defendible tener un motor de palabras clave en un módulo que los
rechazó por escrito: **cuándo NO contesta**, y que contestar no le quita la conversación a nadie.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.business.infrastructure.models import OperatingHoursModel
from restaurante.modules.messaging.infrastructure.models import (
    WhatsAppAutoreplySettingsModel,
    WhatsAppContactModel,
    WhatsAppConversationModel,
    WhatsAppMessageModel,
)
from restaurante.modules.orders.infrastructure.models import OrderModel
from restaurante.shared.database import SessionFactory
from tests.modules.messaging.conftest import (
    create_branch,
    create_employee,
    create_session_row,
    demo_tenant_id,
    post_inbound,
)

LOCATION_FAQ = {
    "id": "faq-location",
    "name": "Ubicación",
    "enabled": True,
    "triggers": ["ubicacion", "direccion", "donde estan"],
    "text": "Estamos en {branch_address}.",
}
HOURS_FAQ = {
    "id": "faq-hours",
    "name": "Horario",
    "enabled": True,
    "triggers": ["horario", "a que hora abren"],
    "text": "Estamos {hours_line}.",
}


async def _settings(**over: object) -> None:
    """Enciende el saludo (para llegar a `greeted`) y deja los ajustes que pida la prueba."""
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


async def _conversation() -> WhatsAppConversationModel:
    async with SessionFactory() as s:
        return (
            (await s.execute(select(WhatsAppConversationModel))).scalars().first()
        )


async def _set_status(status: str) -> None:
    async with SessionFactory() as s:
        row = (await s.execute(select(WhatsAppConversationModel))).scalars().first()
        row.status = status
        await s.commit()


async def _create_live_order(branch_id: uuid.UUID, *, age_hours: float = 0.0) -> None:
    """Un pedido abierto del contacto que escribió, con la antigüedad que pida la prueba."""
    tenant_id = await demo_tenant_id()
    employee_id = await create_employee(branch_id, "faq@demo.com")
    async with SessionFactory() as s:
        contact = (await s.execute(select(WhatsAppContactModel))).scalars().first()
        s.add(
            OrderModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                employee_id=employee_id,
                channel="whatsapp",
                status="open",
                subtotal=Decimal("0"),
                discount=Decimal("0"),
                total=Decimal("0"),
                whatsapp_contact_id=contact.id,
                created_at=datetime.now(UTC) - timedelta(hours=age_hours),
            )
        )
        await s.commit()


async def _setup(
    client: AsyncClient, faqs: list[dict[str, object]] | None
) -> uuid.UUID:
    """Sede abierta, saludo ya dado y conversación en `greeted`. Devuelve la sucursal.

    El saludo es lo que lleva la conversación a `greeted`, que es el único estado en el que las
    FAQs contestan — así que todas las pruebas parten de ahí.
    """
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _settings(faqs=faqs)
    await post_inbound(client, "inst-centro", message_id="m-0")
    return branch


# --- Contesta ----------------------------------------------------------------
async def test_a_greeted_conversation_gets_its_question_answered(
    client: AsyncClient, fake_bridge
) -> None:
    """El hueco que este change existe para tapar: hoy esto no lo contesta nadie."""
    await _setup(client, [LOCATION_FAQ])

    await post_inbound(client, "inst-centro", message_id="m-1", text="¿dónde están?")

    # El saludo y la FAQ: dos mensajes, uno por entrante.
    assert len(fake_bridge.sent) == 2
    _phone, text = fake_bridge.sent[-1]
    assert text.startswith("Estamos en ")


async def test_the_reply_is_recorded_and_leaves_the_thread_where_it_was(
    client: AsyncClient, fake_bridge
) -> None:
    """Contestar NO cambia el estado ni saca el hilo de la bandeja.

    Es la propiedad que hace sobrevivible una coincidencia equivocada: nadie se queda hablando
    con un bot, y una persona ve el hilo igual.
    """
    await _setup(client, [LOCATION_FAQ])
    await post_inbound(client, "inst-centro", message_id="m-1", text="¿dónde están?")

    conversation = await _conversation()
    assert conversation.status == "greeted"
    assert conversation.employee_id is None

    async with SessionFactory() as s:
        rows = list(
            (
                await s.execute(
                    select(WhatsAppMessageModel).where(
                        WhatsAppMessageModel.sender_type == "system"
                    )
                )
            ).scalars()
        )
    # El saludo y la FAQ quedan los dos en el hilo: el agente ve lo que se dijo en su nombre.
    assert len(rows) == 2
    assert any(m.content.startswith("Estamos en ") for m in rows)


async def test_an_unknown_question_is_silence(
    client: AsyncClient, fake_bridge
) -> None:
    await _setup(client, [LOCATION_FAQ])
    await post_inbound(
        client, "inst-centro", message_id="m-1", text="quiero una hamburguesa"
    )
    assert len(fake_bridge.sent) == 1  # sólo el saludo


# --- Los dos gates -----------------------------------------------------------
async def test_a_contact_with_a_live_order_gets_no_faq(
    client: AsyncClient, fake_bridge
) -> None:
    """"mi dirección es…" de alguien que está pidiendo NO es la pregunta de la ubicación.

    Palabra completa no salva este caso —`direccion` es palabra completa ahí—: lo salva el gate.
    """
    branch = await _setup(client, [LOCATION_FAQ])
    await _create_live_order(branch)

    await post_inbound(
        client, "inst-centro", message_id="m-1", text="mi dirección es la calle 5 #3-20"
    )

    assert len(fake_bridge.sent) == 1  # sólo el saludo


async def test_a_stale_order_does_not_silence_faqs_forever(
    client: AsyncClient, fake_bridge
) -> None:
    """Sin ventana, un pedido abandonado calla las FAQs para siempre y nada lo explica."""
    branch = await _setup(client, [LOCATION_FAQ])
    await _create_live_order(branch, age_hours=48)  # fuera de las 24 h por defecto

    await post_inbound(client, "inst-centro", message_id="m-1", text="¿dónde están?")

    assert len(fake_bridge.sent) == 2


async def test_asking_for_a_person_beats_every_faq(
    client: AsyncClient, fake_bridge
) -> None:
    await _setup(client, [LOCATION_FAQ])
    await post_inbound(
        client,
        "inst-centro",
        message_id="m-1",
        text="¿me pasan con alguien? necesito la dirección",
    )
    assert len(fake_bridge.sent) == 1


async def test_wanting_to_cancel_beats_every_faq(
    client: AsyncClient, fake_bridge
) -> None:
    await _setup(client, [LOCATION_FAQ])
    await post_inbound(
        client, "inst-centro", message_id="m-1", text="quiero cancelar, ¿dónde están?"
    )
    assert len(fake_bridge.sent) == 1


# --- Quién es dueño del mensaje ----------------------------------------------
async def test_the_first_message_only_gets_the_greeting(
    client: AsyncClient, fake_bridge
) -> None:
    """Saludo + FAQ serían dos automáticos por un entrante, y el saludo ya lleva el enlace.

    Sale gratis porque el estado se lee antes de saludar, pero se fija aquí: es lo que se rompe
    al refactorizar `handle_inbound`.
    """
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _settings(faqs=[LOCATION_FAQ])

    await post_inbound(client, "inst-centro", message_id="m-1", text="¿dónde están?")

    assert len(fake_bridge.sent) == 1
    _phone, text = fake_bridge.sent[0]
    assert "Bienvenido" in text  # el saludo, no la FAQ


async def test_a_claimed_conversation_is_not_answered_by_a_faq(
    client: AsyncClient, fake_bridge
) -> None:
    await _setup(client, [LOCATION_FAQ])
    await _set_status("human")

    await post_inbound(client, "inst-centro", message_id="m-1", text="¿dónde están?")

    assert len(fake_bridge.sent) == 1


async def test_a_bot_conversation_is_not_answered_by_a_faq(
    client: AsyncClient, fake_bridge
) -> None:
    """El asistente tiene herramientas y redacta mejor; dos voces en un hilo se notan."""
    await _setup(client, [LOCATION_FAQ])
    await _set_status("bot")

    await post_inbound(client, "inst-centro", message_id="m-1", text="¿dónde están?")

    assert len(fake_bridge.sent) == 1


# --- Emisión única -----------------------------------------------------------
async def test_the_same_question_twice_gets_one_answer(
    client: AsyncClient, fake_bridge
) -> None:
    await _setup(client, [LOCATION_FAQ])
    await post_inbound(client, "inst-centro", message_id="m-1", text="¿dónde están?")
    await post_inbound(client, "inst-centro", message_id="m-2", text="¿la dirección?")

    assert len(fake_bridge.sent) == 2  # saludo + UNA respuesta


async def test_a_different_question_is_still_answered(
    client: AsyncClient, fake_bridge
) -> None:
    await _setup(client, [LOCATION_FAQ, HOURS_FAQ])
    await post_inbound(client, "inst-centro", message_id="m-1", text="¿dónde están?")
    await post_inbound(client, "inst-centro", message_id="m-2", text="¿y el horario?")

    assert len(fake_bridge.sent) == 3
    assert fake_bridge.sent[-1][1].startswith("Estamos hoy hasta las")


# --- Cerrado -----------------------------------------------------------------
async def test_a_closed_business_still_answers_its_faqs(
    client: AsyncClient, fake_bridge
) -> None:
    """La excepción deliberada al horario: una FAQ no promete atención, es un cartel."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    tomorrow = (datetime.now(UTC).weekday() + 1) % 7
    await _closed_all_week_except(branch, tomorrow)
    await _settings(faqs=[HOURS_FAQ])
    await post_inbound(client, "inst-centro", message_id="m-0")

    await post_inbound(client, "inst-centro", message_id="m-1", text="¿el horario?")

    _phone, text = fake_bridge.sent[-1]
    assert text.startswith("Estamos cerrados; abrimos ")
    # Y ni una palabra añadida por el sistema: lo que llega es lo que el dueño escribió.
    assert text.endswith(".")
    assert "asistente" not in text.lower()


async def test_a_branch_without_hours_omits_the_sentence_instead_of_the_placeholder(
    client: AsyncClient, fake_bridge
) -> None:
    """El hueco lo lee un CLIENTE, no el dueño en la pantalla: `{hours_line}` no puede salir."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _settings(faqs=[HOURS_FAQ])
    await post_inbound(client, "inst-centro", message_id="m-0")

    await post_inbound(client, "inst-centro", message_id="m-1", text="¿el horario?")

    _phone, text = fake_bridge.sent[-1]
    assert "{hours_line}" not in text


# --- Instalar esto no le cambia el canal a nadie -----------------------------
async def test_a_tenant_who_never_configured_faqs_answers_nothing(
    client: AsyncClient, fake_bridge
) -> None:
    """Las sugeridas llegan APAGADAS: nadie recibe una FAQ sin que el dueño la encienda."""
    await _setup(client, None)  # faqs = NULL

    await post_inbound(client, "inst-centro", message_id="m-1", text="¿dónde están?")

    assert len(fake_bridge.sent) == 1  # sólo el saludo


async def test_deleting_every_faq_sticks(client: AsyncClient, fake_bridge) -> None:
    """`[]` es "decidió que ninguna", y no puede leerse como "nunca las tocó"."""
    await _setup(client, [])

    await post_inbound(client, "inst-centro", message_id="m-1", text="¿dónde están?")

    assert len(fake_bridge.sent) == 1
