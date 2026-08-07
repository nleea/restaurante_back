"""Avisos de estado al cliente: cuáles hablan, cuáles callan, y uno solo por estado.

Lo que se protege aquí no es el texto: es la CUOTA del número. Cuatro mensajes por pedido
es la decisión de producto; ocho hace que WhatsApp marque la cuenta y que el cliente
silencie el chat. Por eso los tests miran tanto lo que sale como lo que NO sale.
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.menu.infrastructure.models import (
    CategoryModel,
    ProductModel,
    ProductVariantModel,
)
from restaurante.modules.messaging.infrastructure.api.deps import (
    build_customer_channel,
)
from restaurante.modules.messaging.infrastructure.models import (
    WhatsAppContactModel,
    WhatsAppConversationModel,
    WhatsAppOutboundEmissionModel,
)
from restaurante.modules.orders.infrastructure.models import OrderItemModel, OrderModel
from restaurante.shared.customer_channel.ports import (
    CUSTOMER_STATE_ASSIGNED,
    CUSTOMER_STATE_AWAITING_PROOF,
    CUSTOMER_STATE_CANCELLED,
    CUSTOMER_STATE_DELIVERED,
    CUSTOMER_STATE_ON_THE_WAY,
    CUSTOMER_STATE_ORDER_RECEIVED,
    CUSTOMER_STATE_READY,
)
from restaurante.shared.database import SessionFactory
from tests.conftest import TEST_EMAIL
from tests.modules.messaging.conftest import (
    create_branch,
    create_employee,
    create_session_row,
    demo_tenant_id,
    login,
    post_inbound,
)

_PHONE = "+573001112233"


async def _contact_id() -> uuid.UUID:
    async with SessionFactory() as s:
        return (
            await s.execute(select(WhatsAppContactModel.id))
        ).scalars().one()


async def _seed_order(
    branch_id: uuid.UUID,
    employee_id: uuid.UUID,
    *,
    contact_id: uuid.UUID | None,
    total: Decimal = Decimal("32000"),
) -> uuid.UUID:
    """Una comanda mínima, atada (o no) al contacto de WhatsApp."""
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            channel="delivery",
            employee_id=employee_id,
            status="open",
            subtotal=total,
            total=total,
            whatsapp_contact_id=contact_id,
        )
        s.add(order)
        await s.commit()
        await s.refresh(order)
        return order.id


async def _seed_line(
    order_id: uuid.UUID,
    branch_id: uuid.UUID,
    *,
    name: str,
    quantity: int,
    line_subtotal: Decimal,
    status: str = "pending",
) -> None:
    """Una línea de la comanda, con su cadena de menú para que tenga nombre que contar."""
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        category = CategoryModel(tenant_id=tenant_id, name="Comida")
        s.add(category)
        await s.flush()
        product = ProductModel(
            tenant_id=tenant_id, category_id=category.id, name=name
        )
        s.add(product)
        await s.flush()
        variant = ProductVariantModel(tenant_id=tenant_id, product_id=product.id)
        s.add(variant)
        await s.flush()
        s.add(
            OrderItemModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                order_id=order_id,
                product_variant_id=variant.id,
                quantity=quantity,
                unit_price=line_subtotal / quantity,
                line_subtotal=line_subtotal,
                status=status,
            )
        )
        await s.commit()


async def _notify(order_id: uuid.UUID, state: str) -> None:
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        await build_customer_channel(s).notify_order_state(tenant_id, order_id, state)


async def _conversation() -> WhatsAppConversationModel:
    """El único hilo del contacto (los tests que abren un segundo lo leen a mano)."""
    async with SessionFactory() as s:
        rows = await s.execute(select(WhatsAppConversationModel))
        return rows.scalars().one()


async def _emissions() -> list[WhatsAppOutboundEmissionModel]:
    async with SessionFactory() as s:
        rows = await s.execute(select(WhatsAppOutboundEmissionModel))
        return list(rows.scalars())


async def _wired(client: AsyncClient) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Sede emparejada + empleado + un cliente que YA nos escribió (y su contacto)."""
    branch_id = await create_branch("centro", primary=True)
    await create_session_row(branch_id, "inst-centro")
    employee_id = await create_employee(branch_id, TEST_EMAIL)
    await post_inbound(client, "inst-centro", message_id="in-1", phone=_PHONE)
    return branch_id, employee_id, await _contact_id()


# --- Los que hablan de fábrica ----------------------------------------------
async def test_mapped_transitions_reach_the_customer(
    client: AsyncClient, fake_bridge
) -> None:
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    await _notify(order_id, CUSTOMER_STATE_ORDER_RECEIVED)
    await _notify(order_id, CUSTOMER_STATE_ON_THE_WAY)
    await _notify(order_id, CUSTOMER_STATE_DELIVERED)

    bodies = [body for _phone, body in fake_bridge.sent]
    assert len(bodies) == 3
    # El número del pedido es el mismo que ve el mostrador (`hex[:8]`, en mayúsculas).
    short = order_id.hex[:8].upper()
    assert short in bodies[0]
    # Y el total sale formateado como se lee en Colombia, no como `32000.00`.
    assert "$32.000" in bodies[0]
    assert "camino" in bodies[1]
    assert "entregado" in bodies[2].lower()


async def test_cancelled_speaks_but_internal_churn_is_silent(
    client: AsyncClient, fake_bridge
) -> None:
    """`ready` y `assigned` existen, pero apagados: son ruido interno para el cliente."""
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    await _notify(order_id, CUSTOMER_STATE_READY)
    await _notify(order_id, CUSTOMER_STATE_ASSIGNED)
    # Estados internos que ni siquiera están en el mapeo.
    await _notify(order_id, "in_progress")
    await _notify(order_id, "preparing")
    assert fake_bridge.sent == []

    await _notify(order_id, CUSTOMER_STATE_CANCELLED)
    assert len(fake_bridge.sent) == 1
    assert "cancelado" in fake_bridge.sent[0][1]


async def test_ready_speaks_when_a_pickup_tenant_opts_in(
    client: AsyncClient, fake_bridge
) -> None:
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    headers = await login(client)
    resp = await client.put(
        "/messaging/autoreply",
        headers=headers,
        json={
            "greeting_enabled": False,
            "greeting_open_text": "",
            "greeting_closed_text": "",
            "assistant_offer_enabled": False,
            "idle_hours": 24,
            "token_lifetime_hours": 24,
            "status_mapping": {
                "ready": {"enabled": True, "text": "Listo para recoger, {order_number}."}
            },
        },
    )
    assert resp.status_code == 200, resp.text

    await _notify(order_id, CUSTOMER_STATE_READY)

    assert len(fake_bridge.sent) == 1
    assert "Listo para recoger" in fake_bridge.sent[0][1]
    # Encender `ready` no puede haber apagado los otros: el mapeo del tenant se SUPERPONE
    # al de fábrica, no lo reemplaza.
    await _notify(order_id, CUSTOMER_STATE_ON_THE_WAY)
    assert len(fake_bridge.sent) == 2


# --- El detalle de lo pedido --------------------------------------------------
async def test_the_receipt_carries_what_was_ordered(
    client: AsyncClient, fake_bridge
) -> None:
    """El acuse lista los productos. Un total suelto obliga a confiar en un número.

    Y el que sale es el precio de LA LÍNEA, no el unitario: quien recibe "2x Hamburguesa ·
    $12.500" cree que le cobraron de más.
    """
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)
    await _seed_line(
        order_id,
        branch_id,
        name="Hamburguesa",
        quantity=2,
        line_subtotal=Decimal("25000"),
    )
    await _seed_line(
        order_id, branch_id, name="Limonada", quantity=1, line_subtotal=Decimal("7000")
    )
    # Lo que se anuló ya no lo tiene: cobrárselo en el chat es una discusión en la puerta.
    await _seed_line(
        order_id,
        branch_id,
        name="Papas",
        quantity=1,
        line_subtotal=Decimal("9000"),
        status="cancelled",
    )

    await _notify(order_id, CUSTOMER_STATE_ORDER_RECEIVED)

    body = fake_bridge.sent[0][1]
    assert "2x Hamburguesa · $25.000" in body
    assert "1x Limonada · $7.000" in body
    assert "Papas" not in body
    assert "$32.000" in body  # el total sigue estando


async def test_the_other_states_do_not_repeat_the_list(
    client: AsyncClient, fake_bridge
) -> None:
    """Repetir el detalle en cada aviso convierte el chat en un catálogo."""
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)
    await _seed_line(
        order_id,
        branch_id,
        name="Hamburguesa",
        quantity=2,
        line_subtotal=Decimal("25000"),
    )

    await _notify(order_id, CUSTOMER_STATE_ON_THE_WAY)

    assert "Hamburguesa" not in fake_bridge.sent[0][1]


# --- La entrega cierra el hilo ------------------------------------------------
async def test_delivery_closes_the_conversation(
    client: AsyncClient, fake_bridge
) -> None:
    """Un pedido entregado es una conversación acabada — igual que el botón de la bandeja.

    Y se cierra DESPUÉS de avisar: el "fue entregado" tiene que quedar dentro del hilo.
    """
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    await _notify(order_id, CUSTOMER_STATE_ON_THE_WAY)
    assert (await _conversation()).status != "closed"

    await _notify(order_id, CUSTOMER_STATE_DELIVERED)

    conversation = await _conversation()
    assert conversation.status == "closed"
    assert conversation.closed_at is not None
    assert "entregado" in fake_bridge.sent[-1][1].lower()


async def test_delivery_closes_even_with_the_notice_switched_off(
    client: AsyncClient, fake_bridge
) -> None:
    """Cerrar es operativo (el pedido acabó), no la consecuencia de haber hablado."""
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    headers = await login(client)
    resp = await client.put(
        "/messaging/autoreply",
        headers=headers,
        json={
            "greeting_enabled": False,
            "greeting_open_text": "",
            "greeting_closed_text": "",
            "assistant_offer_enabled": False,
            "idle_hours": 24,
            "token_lifetime_hours": 24,
            "status_mapping": {"delivered": {"enabled": False, "text": ""}},
        },
    )
    assert resp.status_code == 200, resp.text

    await _notify(order_id, CUSTOMER_STATE_DELIVERED)

    assert fake_bridge.sent == []
    assert (await _conversation()).status == "closed"


async def test_a_cancelled_order_keeps_the_thread_open(
    client: AsyncClient, fake_bridge
) -> None:
    """"¿Por qué me lo cancelaron?" es justo la conversación que NO se puede colgar."""
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    await _notify(order_id, CUSTOMER_STATE_CANCELLED)

    assert (await _conversation()).status != "closed"


async def test_the_customer_who_writes_again_gets_a_fresh_thread(
    client: AsyncClient, fake_bridge
) -> None:
    """Cerrar no es echar al cliente: el que vuelve a escribir abre un hilo nuevo.

    (Nace en `new`, no en `greeted`, porque el saludo viene apagado de fábrica; encendido,
    este es el cliente que vuelve a recibir el enlace de la carta.)
    """
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)
    await _notify(order_id, CUSTOMER_STATE_DELIVERED)

    await post_inbound(client, "inst-centro", message_id="in-2", phone=_PHONE)

    async with SessionFactory() as s:
        rows = list(
            (await s.execute(select(WhatsAppConversationModel))).scalars()
        )
    assert len(rows) == 2
    assert sorted(c.status for c in rows) == ["closed", "new"]


# --- Emitir una sola vez ------------------------------------------------------
async def test_a_bouncing_status_sends_exactly_one(
    client: AsyncClient, fake_bridge
) -> None:
    """La entrega rebota `in_transit` ⇄ `assigned`; el cliente ve UN "va en camino"."""
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    for _ in range(4):
        await _notify(order_id, CUSTOMER_STATE_ON_THE_WAY)

    assert len(fake_bridge.sent) == 1
    assert len(await _emissions()) == 1


async def test_concurrent_claims_send_exactly_one(
    client: AsyncClient, fake_bridge
) -> None:
    """Dos workers a la vez. Lo que decide es la constraint, no un `if ya_enviamos`.

    Con un `if last_sent_at is None` ambos leerían "todavía nadie envió" y el cliente
    recibiría el mismo aviso dos veces.
    """
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    await asyncio.gather(
        _notify(order_id, CUSTOMER_STATE_ON_THE_WAY),
        _notify(order_id, CUSTOMER_STATE_ON_THE_WAY),
        _notify(order_id, CUSTOMER_STATE_ON_THE_WAY),
    )

    assert len(fake_bridge.sent) == 1


async def test_two_states_of_one_order_are_two_emissions(
    client: AsyncClient, fake_bridge
) -> None:
    """La clave es (pedido, estado): dedup no puede significar "un mensaje por pedido"."""
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    await _notify(order_id, CUSTOMER_STATE_ON_THE_WAY)
    await _notify(order_id, CUSTOMER_STATE_DELIVERED)

    assert len(fake_bridge.sent) == 2
    assert len(await _emissions()) == 2


# --- Sin nadie a quien avisar -------------------------------------------------
async def test_an_order_without_a_whatsapp_customer_says_nothing(
    client: AsyncClient, fake_bridge
) -> None:
    """Una comanda de mostrador no le habla a nadie, y eso no es un error."""
    branch_id, employee_id, _contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=None)

    await _notify(order_id, CUSTOMER_STATE_ON_THE_WAY)

    assert fake_bridge.sent == []
    assert await _emissions() == []


async def test_an_unreachable_contact_never_gets_a_message(
    client: AsyncClient, fake_bridge
) -> None:
    """Un contacto que nunca escribió no recibe nada — y la transición no se entera.

    Es el guard el que lo impide, no este módulo: el aviso sale por el MISMO gateway
    guardado que todo lo demás.
    """
    branch_id, employee_id, _real_contact = await _wired(client)
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        ghost = WhatsAppContactModel(
            tenant_id=tenant_id, phone="+573009998877", name="Nunca escribió"
        )
        s.add(ghost)
        await s.flush()
        s.add(
            WhatsAppConversationModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                whatsapp_contact_id=ghost.id,
                status="greeted",
            )
        )
        await s.commit()
        ghost_id = ghost.id

    order_id = await _seed_order(branch_id, employee_id, contact_id=ghost_id)

    # No levanta: quien llama está en mitad de una transición ya decidida.
    await _notify(order_id, CUSTOMER_STATE_ON_THE_WAY)

    assert fake_bridge.sent == []


async def test_a_dead_bridge_never_fails_the_transition(
    client: AsyncClient, fake_bridge
) -> None:
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)
    fake_bridge.fail = True

    await _notify(order_id, CUSTOMER_STATE_ON_THE_WAY)

    assert fake_bridge.sent == []


# --- El acuse de un pedido que nace debiendo ---------------------------------
async def test_awaiting_proof_is_enabled_by_default_and_says_what_is_missing(
    client: AsyncClient, fake_bridge
) -> None:
    """Reemplaza al acuse normal: dice que el pedido está guardado y por qué no está en cocina."""
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    await _notify(order_id, CUSTOMER_STATE_AWAITING_PROOF)

    body = fake_bridge.sent[0][1]
    assert order_id.hex[:8].upper() in body
    assert "$32.000" in body
    assert "entra a cocina" in body
    # No EXIGE el comprobante: el cliente puede haberlo adjuntado ya en el checkout, y pedirle lo
    # que acaba de mandar se lee como que no llegó.
    assert "puedes mandarlo" in body


async def test_a_prepaid_order_gets_one_acknowledgement_not_two(
    client: AsyncClient, fake_bridge
) -> None:
    """El techo de cuatro mensajes por pedido es la defensa principal del módulo.

    Los dos acuses son mutuamente excluyentes; quien los mande los dos ha roto el change aunque
    todo lo demás pase.
    """
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    # El recorrido de un prepago: acuse de "esperando pago", va en camino, entregado.
    await _notify(order_id, CUSTOMER_STATE_AWAITING_PROOF)
    await _notify(order_id, CUSTOMER_STATE_ON_THE_WAY)
    await _notify(order_id, CUSTOMER_STATE_DELIVERED)

    bodies = [body for _phone, body in fake_bridge.sent]
    assert len(bodies) == 3, "un prepago no manda más mensajes que uno en efectivo"
    assert sum(1 for b in bodies if "Recibimos tu pedido" in b) == 1
