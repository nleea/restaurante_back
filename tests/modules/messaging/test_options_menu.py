"""El menú de opciones: que un chat abierto no se quede mudo.

`test_faq_replies.py` fija cuándo una FAQ contesta y cuándo calla. Aquí se prueba la red que
existe DEBAJO de las FAQs: cuando ni el saludo, ni el asistente, ni una FAQ contestaron, un
mensaje en una conversación abierta recibe un menú de opciones en vez de silencio.

Las dos propiedades que lo hacen defendible, y que estas pruebas fijan:
- sale **una vez por conversación** —no en cada mensaje no entendido—, y
- **no sale** en `human`, `closed` ni con el negocio cerrado.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.business.infrastructure.models import OperatingHoursModel
from restaurante.modules.messaging.infrastructure.models import (
    WhatsAppAutoreplySettingsModel,
    WhatsAppContactModel,
    WhatsAppConversationModel,
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


async def _settings(**over: object) -> None:
    """Enciende saludo y menú, y deja los ajustes que pida la prueba."""
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
        row.menu_enabled = True
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
        return (await s.execute(select(WhatsAppConversationModel))).scalars().first()


async def _set_status(status: str) -> None:
    async with SessionFactory() as s:
        row = (await s.execute(select(WhatsAppConversationModel))).scalars().first()
        row.status = status
        await s.commit()


async def _create_order(branch_id: uuid.UUID, *, status: str = "open") -> uuid.UUID:
    """Un pedido del contacto que escribió, para probar la opción de estado."""
    tenant_id = await demo_tenant_id()
    employee_id = await create_employee(branch_id, "menu@demo.com")
    async with SessionFactory() as s:
        contact = (await s.execute(select(WhatsAppContactModel))).scalars().first()
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            employee_id=employee_id,
            channel="whatsapp",
            status=status,
            subtotal=Decimal("46000"),
            discount=Decimal("0"),
            total=Decimal("46000"),
            whatsapp_contact_id=contact.id,
            created_at=datetime.now(UTC),
        )
        s.add(order)
        await s.commit()
        await s.refresh(order)
        return order.id


async def _setup(
    client: AsyncClient, *, menu_enabled: bool = True
) -> uuid.UUID:
    """Sede abierta, saludo ya dado y conversación en `greeted`. Devuelve la sucursal."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _settings(menu_enabled=menu_enabled)
    await post_inbound(client, "inst-centro", message_id="m-0")
    return branch


# --- El hueco que esto tapa --------------------------------------------------
async def test_an_unmatched_message_gets_the_menu(
    client: AsyncClient, fake_bridge
) -> None:
    await _setup(client)

    await post_inbound(
        client, "inst-centro", message_id="m-1", text="quiero una hamburguesa"
    )

    assert len(fake_bridge.sent) == 2  # saludo + menú
    _phone, text = fake_bridge.sent[-1]
    assert "*1*" in text
    assert "*2*" in text
    assert "*3*" in text


async def test_the_first_message_only_gets_the_greeting(
    client: AsyncClient, fake_bridge
) -> None:
    """Dos automáticos por un entrante es lo que WhatsApp castiga; el saludo ya lleva el enlace."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _settings()

    await post_inbound(client, "inst-centro", message_id="m-1", text="quiero una hamburguesa")

    assert len(fake_bridge.sent) == 1
    assert "Bienvenido" in fake_bridge.sent[0][1]


async def test_the_menu_is_sent_only_once_per_conversation(
    client: AsyncClient, fake_bridge
) -> None:
    await _setup(client)
    await post_inbound(client, "inst-centro", message_id="m-1", text="bles")
    await post_inbound(client, "inst-centro", message_id="m-2", text="cualquier cosa")

    assert len(fake_bridge.sent) == 2  # saludo + UN menú


async def test_a_disabled_menu_keeps_the_old_silence(
    client: AsyncClient, fake_bridge
) -> None:
    """Apagado por defecto: instalar esto no le cambia el canal a nadie."""
    await _setup(client, menu_enabled=False)

    await post_inbound(client, "inst-centro", message_id="m-1", text="quiero una hamburguesa")

    assert len(fake_bridge.sent) == 1


async def test_a_closed_business_does_not_get_the_menu(
    client: AsyncClient, fake_bridge
) -> None:
    """Ofrecer "haz un pedido" a las once de la noche es prometer lo que no hay."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    tomorrow = (datetime.now(UTC).weekday() + 1) % 7
    await _closed_all_week_except(branch, tomorrow)
    await _settings()
    await post_inbound(client, "inst-centro", message_id="m-0")

    await post_inbound(client, "inst-centro", message_id="m-1", text="quiero una hamburguesa")

    assert len(fake_bridge.sent) == 1  # sólo el saludo de cerrado


async def test_a_branch_without_hours_does_get_the_menu(
    client: AsyncClient, fake_bridge
) -> None:
    """Sin horarios no hay un "cerrado" que respetar; callar por eso es el silencio a evitar."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _settings()
    await post_inbound(client, "inst-centro", message_id="m-0")

    await post_inbound(client, "inst-centro", message_id="m-1", text="quiero una hamburguesa")

    assert len(fake_bridge.sent) == 2


async def test_a_human_conversation_gets_no_menu(
    client: AsyncClient, fake_bridge
) -> None:
    await _setup(client)
    await _set_status("human")

    await post_inbound(client, "inst-centro", message_id="m-1", text="quiero una hamburguesa")

    assert len(fake_bridge.sent) == 1


async def test_a_bot_conversation_gets_no_menu(
    client: AsyncClient, fake_bridge
) -> None:
    await _setup(client)
    await _set_status("bot")

    await post_inbound(client, "inst-centro", message_id="m-1", text="quiero una hamburguesa")

    assert len(fake_bridge.sent) == 1


# --- Las opciones contestan de verdad ----------------------------------------
async def test_the_order_option_sends_the_store_link(
    client: AsyncClient, fake_bridge
) -> None:
    await _setup(client)

    await post_inbound(client, "inst-centro", message_id="m-1", text="pedido")

    assert len(fake_bridge.sent) == 2
    _phone, text = fake_bridge.sent[-1]
    assert "/store" in text
    assert "?t=" in text


async def test_the_status_option_reports_the_latest_order(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await _setup(client)
    await _create_order(branch)

    await post_inbound(client, "inst-centro", message_id="m-1", text="estado")

    _phone, text = fake_bridge.sent[-1]
    assert text.startswith("Tu pedido ")
    assert "recibimos" in text
    assert "$46.000" in text


async def test_the_status_option_without_orders_offers_the_menu_link(
    client: AsyncClient, fake_bridge
) -> None:
    await _setup(client)

    await post_inbound(client, "inst-centro", message_id="m-1", text="estado")

    _phone, text = fake_bridge.sent[-1]
    assert "No encuentro pedidos recientes" in text
    assert "/store" in text


async def test_the_person_option_hands_the_thread_to_a_human(
    client: AsyncClient, fake_bridge
) -> None:
    await _setup(client)

    await post_inbound(client, "inst-centro", message_id="m-1", text="persona")

    _phone, text = fake_bridge.sent[-1]
    assert "equipo" in text
    conversation = await _conversation()
    assert conversation.status == "human"
    assert conversation.employee_id is None


async def test_asking_for_a_person_in_greeted_hands_off(
    client: AsyncClient, fake_bridge
) -> None:
    """"quiero hablar con una persona" no es una opción que el menú enseñe, pero sale igual."""
    await _setup(client)

    await post_inbound(
        client, "inst-centro", message_id="m-1", text="quiero hablar con una persona"
    )

    _phone, text = fake_bridge.sent[-1]
    assert "equipo" in text
    assert (await _conversation()).status == "human"


async def test_a_recognised_option_is_answered_only_once(
    client: AsyncClient, fake_bridge
) -> None:
    await _setup(client)
    await post_inbound(client, "inst-centro", message_id="m-1", text="pedido")
    await post_inbound(client, "inst-centro", message_id="m-2", text="pedido")

    assert len(fake_bridge.sent) == 2  # saludo + UN enlace


async def test_a_number_inside_a_sentence_is_not_an_option(
    client: AsyncClient, fake_bridge
) -> None:
    """"quiero 2 hamburguesas" NO es una consulta de estado; es un pedido mal escrito."""
    await _setup(client)

    await post_inbound(
        client, "inst-centro", message_id="m-1", text="quiero 2 hamburguesas"
    )

    _phone, text = fake_bridge.sent[-1]
    assert "No encuentro pedidos" not in text
    assert "Dime qué necesitas" in text  # el menú, no una opción


async def test_a_lone_number_is_an_option(client: AsyncClient, fake_bridge) -> None:
    await _setup(client)

    await post_inbound(client, "inst-centro", message_id="m-1", text="2")

    _phone, text = fake_bridge.sent[-1]
    assert "No encuentro pedidos" in text


# --- Sin saludo: el menú es el único automatismo ------------------------------
async def _settings_without_greeting() -> None:
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
        row.greeting_enabled = False
        row.menu_enabled = True
        await s.commit()


async def test_the_menu_works_without_a_greeting(
    client: AsyncClient, fake_bridge
) -> None:
    """Un tenant que no saluda pero sí quiere menú: el primer mensaje ya recibe respuesta."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _settings_without_greeting()

    await post_inbound(client, "inst-centro", message_id="m-1", text="quiero una hamburguesa")

    assert len(fake_bridge.sent) == 1
    assert "*2*" in fake_bridge.sent[-1][1]


async def test_an_option_works_without_a_greeting(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    await _settings_without_greeting()

    await post_inbound(client, "inst-centro", message_id="m-1", text="pedido")

    assert len(fake_bridge.sent) == 1
    assert "/store" in fake_bridge.sent[-1][1]

