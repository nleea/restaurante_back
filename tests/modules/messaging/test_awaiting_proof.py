"""Un pedido que nace debiendo: el aviso que lo dice y el saludo que lo reconoce.

Dos afirmaciones sostienen el fichero:

- **`awaiting_proof` SUSTITUYE al acuse normal, no se suma.** Dos mensajes por el mismo hecho es el
  volumen de salida que hace que WhatsApp mire un número, y el techo de cuatro por pedido es la
  defensa principal del módulo.
- **La tercera variante del saludo se elige por el ESTADO del pedido, nunca por el texto.** Es lo
  que la hace compatible con la regla #1: el saludo sigue sin leer lo que el cliente escribió.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.cash.infrastructure.models import CashSessionModel
from restaurante.modules.messaging.infrastructure.models import (
    WhatsAppAutoreplySettingsModel,
    WhatsAppContactModel,
    WhatsAppMessageModel,
)
from restaurante.modules.orders.infrastructure.models import OrderModel, OrderPaymentModel
from restaurante.shared.database import SessionFactory
from tests.modules.messaging.conftest import (
    create_branch,
    create_employee,
    create_session_row,
    demo_tenant_id,
    post_inbound,
)


async def _settings(**over: object) -> None:
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


async def _order(
    branch_id: uuid.UUID,
    *,
    method: str | None = "transfer",
    total: str = "46000",
    paid: str | None = None,
    age_hours: float = 0.0,
    status: str = "open",
) -> uuid.UUID:
    """Un pedido de quien escribió, con el método, el saldo y la antigüedad que pida la prueba."""
    tenant_id = await demo_tenant_id()
    employee_id = await create_employee(branch_id, "proof@demo.com")
    async with SessionFactory() as s:
        contact = (await s.execute(select(WhatsAppContactModel))).scalars().first()
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            employee_id=employee_id,
            channel="whatsapp",
            status=status,
            payment_method=method,
            subtotal=Decimal(total),
            discount=Decimal("0"),
            total=Decimal(total),
            whatsapp_contact_id=contact.id,
            created_at=datetime.now(UTC) - timedelta(hours=age_hours),
        )
        s.add(order)
        await s.flush()
        if paid is not None:
            # Un pago cuelga de una sesión de caja: sin caja abierta no hay dinero registrado en
            # ninguna pantalla, y la columna lo impone.
            cash_session = CashSessionModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                opened_by_employee_id=employee_id,
                opening_amount=Decimal("0"),
                status="open",
            )
            s.add(cash_session)
            await s.flush()
            s.add(
                OrderPaymentModel(
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    order_id=order.id,
                    cash_session_id=cash_session.id,
                    employee_id=employee_id,
                    amount=Decimal(paid),
                    method=method or "cash",
                )
            )
        await s.commit()
        return order.id


AWAITING_TEXT = "¡Hola! Vimos tu pedido {order_number} por {order_total}. Mándanos el comprobante."


# --- El saludo que reconoce el pedido ----------------------------------------
async def test_the_greeting_names_the_order_awaiting_payment(
    client: AsyncClient, fake_bridge
) -> None:
    """Sin esto, quien manda su comprobante recibe "Bienvenido, mira nuestra carta" encima."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _settings(greeting_awaiting_payment_text=AWAITING_TEXT)
    # Primer mensaje: crea el contacto. El saludo sale con la variante normal porque aún no hay
    # pedido; lo que se prueba viene en la SEGUNDA conversación.
    await post_inbound(client, "inst-centro", message_id="m-0")
    order_id = await _order(branch)

    # Se fuerza una conversación nueva cerrando la actual por inactividad.
    async with SessionFactory() as s:
        rows = await s.execute(select(WhatsAppMessageModel))
        for row in rows.scalars():
            row.sent_at = datetime.now(UTC) - timedelta(hours=48)
        await s.commit()

    await post_inbound(client, "inst-centro", message_id="m-1", text="hola")

    _phone, text = fake_bridge.sent[-1]
    assert order_id.hex[:8].upper() in text
    assert "$46.000" in text
    assert "Bienvenido" not in text


async def test_the_variant_does_not_read_the_message(
    client: AsyncClient, fake_bridge
) -> None:
    """La misma variante sale con una foto sin pie, con "hola" o con cualquier palabra.

    Es lo que mantiene intacta la regla #1 del módulo: el saludo no detecta intención.
    """
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _settings(greeting_awaiting_payment_text=AWAITING_TEXT)
    await post_inbound(client, "inst-centro", message_id="m-0")
    await _order(branch)
    async with SessionFactory() as s:
        rows = await s.execute(select(WhatsAppMessageModel))
        for row in rows.scalars():
            row.sent_at = datetime.now(UTC) - timedelta(hours=48)
        await s.commit()

    await post_inbound(client, "inst-centro", message_id="m-1", text="cualquier cosa")

    _phone, text = fake_bridge.sent[-1]
    assert "Mándanos el comprobante" in text


async def test_an_empty_variant_falls_back_instead_of_going_silent(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _settings(greeting_awaiting_payment_text="")
    await post_inbound(client, "inst-centro", message_id="m-0")
    await _order(branch)
    async with SessionFactory() as s:
        rows = await s.execute(select(WhatsAppMessageModel))
        for row in rows.scalars():
            row.sent_at = datetime.now(UTC) - timedelta(hours=48)
        await s.commit()

    await post_inbound(client, "inst-centro", message_id="m-1")

    _phone, text = fake_bridge.sent[-1]
    assert "Bienvenido" in text


async def test_a_settled_order_gets_the_ordinary_greeting(
    client: AsyncClient, fake_bridge
) -> None:
    """Ya pagó: no hay nada que pedirle."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _settings(greeting_awaiting_payment_text=AWAITING_TEXT)
    await post_inbound(client, "inst-centro", message_id="m-0")
    await _order(branch, paid="46000")
    async with SessionFactory() as s:
        rows = await s.execute(select(WhatsAppMessageModel))
        for row in rows.scalars():
            row.sent_at = datetime.now(UTC) - timedelta(hours=48)
        await s.commit()

    await post_inbound(client, "inst-centro", message_id="m-1")

    _phone, text = fake_bridge.sent[-1]
    assert "Bienvenido" in text


async def test_a_cash_order_gets_the_ordinary_greeting(
    client: AsyncClient, fake_bridge
) -> None:
    """En efectivo no debe nada por adelantado: se cobra en la puerta."""
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _settings(greeting_awaiting_payment_text=AWAITING_TEXT)
    await post_inbound(client, "inst-centro", message_id="m-0")
    await _order(branch, method="cash")
    async with SessionFactory() as s:
        rows = await s.execute(select(WhatsAppMessageModel))
        for row in rows.scalars():
            row.sent_at = datetime.now(UTC) - timedelta(hours=48)
        await s.commit()

    await post_inbound(client, "inst-centro", message_id="m-1")

    _phone, text = fake_bridge.sent[-1]
    assert "Bienvenido" in text
