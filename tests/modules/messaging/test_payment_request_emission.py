"""La entrega por WhatsApp del enlace de pago de un domicilio.

Este mensaje no es un aviso: pide dinero. Por eso se prueba distinto que los estados —lo que
importa aquí es que la cifra sea la del servidor, que salga UNA vez por solicitud, y que quien
lo dispara se entere de si llegó, porque el enlace no se puede reenviar.
"""

from __future__ import annotations

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
    EMISSION_NO_CONTACT,
    EMISSION_SENT,
)
from restaurante.shared.database import SessionFactory
from tests.conftest import TEST_EMAIL
from tests.modules.messaging.conftest import (
    create_branch,
    create_employee,
    create_session_row,
    demo_tenant_id,
    post_inbound,
)

_PHONE = "+573001112233"
_URL = "https://demo.wsquote.uk/payment/delivery/tok-abc"


async def _contact_id() -> uuid.UUID:
    async with SessionFactory() as s:
        return (await s.execute(select(WhatsAppContactModel.id))).scalars().one()


async def _seed_order(
    branch_id: uuid.UUID,
    employee_id: uuid.UUID,
    *,
    contact_id: uuid.UUID | None,
    total: Decimal = Decimal("37000"),
) -> uuid.UUID:
    """Un domicilio ya cotizado: $32.000 de comida + $5.000 congelados de domicilio."""
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            channel="delivery",
            employee_id=employee_id,
            status="open",
            subtotal=Decimal("32000"),
            delivery_fee=Decimal("5000"),
            total=total,
            whatsapp_contact_id=contact_id,
        )
        s.add(order)
        await s.commit()
        await s.refresh(order)
        order_id = order.id

        category = CategoryModel(tenant_id=tenant_id, name="Comida")
        s.add(category)
        await s.flush()
        product = ProductModel(
            tenant_id=tenant_id, category_id=category.id, name="Bandeja"
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
                quantity=2,
                unit_price=Decimal("16000"),
                line_subtotal=Decimal("32000"),
                status="pending",
            )
        )
        await s.commit()
        return order_id


async def _emit(order_id: uuid.UUID, *, request_id: uuid.UUID | None = None):
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        return await build_customer_channel(s).notify_delivery_payment_request(
            tenant_id,
            order_id,
            request_id=request_id or uuid.uuid4(),
            payment_url=_URL,
            delivery_fee=Decimal("5000"),
        )


async def _wired(client: AsyncClient) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    branch_id = await create_branch("centro", primary=True)
    await create_session_row(branch_id, "inst-centro")
    employee_id = await create_employee(branch_id, TEST_EMAIL)
    await post_inbound(client, "inst-centro", message_id="in-1", phone=_PHONE)
    return branch_id, employee_id, await _contact_id()


async def test_a_reachable_customer_gets_the_total_and_the_link(
    client: AsyncClient, fake_bridge
) -> None:
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    outcome = await _emit(order_id)

    assert outcome.sent is True
    assert outcome.status == EMISSION_SENT
    assert len(fake_bridge.sent) == 1
    phone, body = fake_bridge.sent[0]
    # El puente normaliza el número (sin `+`) antes de mandarlo.
    assert phone == _PHONE.lstrip("+")
    # El número que ve el mostrador, para que el cliente y el negocio hablen del mismo pedido.
    assert order_id.hex[:8].upper() in body
    # El domicilio DESGLOSADO: es la cifra nueva, la única que el cliente no conocía.
    assert "Domicilio: $5.000" in body
    # Y el total del servidor, no una suma hecha en el mensaje.
    assert "$37.000" in body
    assert _URL in body


async def test_the_same_request_never_sends_twice(
    client: AsyncClient, fake_bridge
) -> None:
    """Dos pasadas del worker sobre la misma solicitud son UN mensaje. Lo garantiza la
    constraint de unicidad, no un `if ya_enviamos`."""
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)
    request_id = uuid.uuid4()

    first = await _emit(order_id, request_id=request_id)
    second = await _emit(order_id, request_id=request_id)

    assert len(fake_bridge.sent) == 1
    # El segundo dice "sent" igualmente: para quien llama lo que importa es que el cliente lo
    # tiene, no quién lo mandó.
    assert first.sent and second.sent


async def test_a_new_request_for_the_same_order_does_send(
    client: AsyncClient, fake_bridge
) -> None:
    """Re-cotizar acuña una solicitud nueva, y ésa SÍ tiene que salir: el total cambió."""
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    await _emit(order_id, request_id=uuid.uuid4())
    await _emit(order_id, request_id=uuid.uuid4())

    assert len(fake_bridge.sent) == 2


async def test_a_repeat_customer_with_a_closed_thread_still_gets_the_link(
    client: AsyncClient, fake_bridge
) -> None:
    """El caso del cliente BUENO, y el que rompía el flujo en producción.

    El hilo se cierra en `delivered`, así que todo el que repite llega aquí cerrado. Rendirse
    ante eso dejaba sin poder pagar justo a quien más pide. Reabrir no es iniciar: `is_reachable`
    sigue exigiendo que ese teléfono nos haya escrito.
    """
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    async with SessionFactory() as s:
        convo = (
            await s.execute(select(WhatsAppConversationModel))
        ).scalars().one()
        convo.status = "closed"
        await s.commit()
        convo_id = convo.id

    outcome = await _emit(order_id)

    assert outcome.sent is True
    assert len(fake_bridge.sent) == 1
    assert _URL in fake_bridge.sent[0][1]
    async with SessionFactory() as s:
        reopened = await s.get(WhatsAppConversationModel, convo_id)
        assert reopened is not None
        assert reopened.status != "closed", "el hilo queda abierto para que el cliente responda"


async def test_a_contact_with_no_thread_at_all_is_not_cold_messaged(
    client: AsyncClient, fake_bridge
) -> None:
    """Reabrir un hilo cerrado sí; inventar uno donde nunca hubo, no. Eso es iniciar."""
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    async with SessionFactory() as s:
        for convo in (
            await s.execute(select(WhatsAppConversationModel))
        ).scalars():
            await s.delete(convo)
        await s.commit()

    outcome = await _emit(order_id)

    assert outcome.sent is False
    assert fake_bridge.sent == []


async def test_an_order_nobody_wrote_from_gets_no_message(
    client: AsyncClient, fake_bridge
) -> None:
    """Un pedido de mostrador no tiene a quién escribirle. No es un fallo."""
    branch_id, employee_id, _contact = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=None)

    outcome = await _emit(order_id)

    assert outcome.sent is False
    assert outcome.status == EMISSION_NO_CONTACT
    assert outcome.reason
    assert fake_bridge.sent == []


async def test_the_raw_token_never_reaches_the_emission_table(
    client: AsyncClient, fake_bridge
) -> None:
    """La clave de deduplicación es el id de la solicitud, NO la URL.

    Usar la URL escribiría el token de pago en claro en la base — justo la credencial que la
    solicitud se molesta en guardar hasheada.
    """
    branch_id, employee_id, contact_id = await _wired(client)
    order_id = await _seed_order(branch_id, employee_id, contact_id=contact_id)

    await _emit(order_id)

    async with SessionFactory() as s:
        keys = [
            row.dedupe_key
            for row in (await s.execute(select(WhatsAppOutboundEmissionModel))).scalars()
        ]
    assert keys
    assert all("tok-abc" not in key for key in keys)
