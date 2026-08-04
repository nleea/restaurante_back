"""El escalado a WhatsApp: el primer envío automático a alguien que no es cliente.

Lo que se prueba no es "¿llega?" sino las cuatro cosas que lo acotan, porque cualquiera de
las cuatro que falle convierte esto en un número bloqueado:

1. el plazo, 2. que alguien la tome, 3. que la regla lo tenga encendido, y 4. el guardián
del canal, que rechaza escribir a quien no escribió primero.

Y la quinta, que es de otro tipo: **se anota aunque no salga**. Un envío fallido que se
reintenta en cada barrido le escribe al mismo número cada cinco minutos.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from restaurante.modules.alerts.application.use_cases.lifecycle import AlertLifecycle
from restaurante.modules.alerts.domain.entities import RULE_LOW_STOCK, AlertRule
from restaurante.modules.alerts.domain.ports import Subject
from restaurante.modules.alerts.infrastructure.models import AlertModel
from restaurante.modules.alerts.infrastructure.repositories import (
    SqlAlchemyAlertRepository,
)
from restaurante.modules.alerts.infrastructure.whatsapp_escalation import (
    ESCALATION_PERMISSION,
    WhatsAppEscalationChannel,
)
from restaurante.modules.identity.infrastructure.models import PersonModel
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from tests.modules.alerts.conftest import (
    create_demo_employee,
    demo_tenant_id,
    link_chat,
    subscribe_to_alerts,
    tracked_session,
)
from tests.modules.messaging.conftest import (
    create_session_row,
    grant_only,
    post_inbound,
)

pytestmark = pytest.mark.asyncio

TOMATO = Subject(ref="ing-tomate", label="Tomate", detail="quedan 2 de 10")


async def _give_phone(employee_id: uuid.UUID, phone: str) -> None:
    """Le pone teléfono a la persona detrás del empleado."""
    async with SessionFactory() as s:
        person_id = (
            await s.execute(
                select(EmployeeModel.person_id).where(EmployeeModel.id == employee_id)
            )
        ).scalar_one()
        await s.execute(
            update(PersonModel).where(PersonModel.id == person_id).values(phone=phone)
        )
        await s.commit()


async def _age(alert_id: uuid.UUID, minutes: int) -> None:
    """Envejece la alerta: probar un plazo esperando no es una prueba."""
    async with SessionFactory() as s:
        row = await s.get(AlertModel, alert_id)
        assert row is not None
        row.fired_at = datetime.now(UTC) - timedelta(minutes=minutes)
        await s.commit()


async def _fire_and_age(branch_id: uuid.UUID, minutes: int = 45) -> uuid.UUID:
    tenant_id = await demo_tenant_id()
    repo = SqlAlchemyAlertRepository(tracked_session())
    lifecycle = AlertLifecycle(repo)
    await lifecycle.save_rule(
        AlertRule(
            tenant_id=tenant_id,
            branch_id=branch_id,
            rule_key=RULE_LOW_STOCK,
            is_enabled=True,
            escalate_to_whatsapp=True,
            escalation_after_minutes=30,
        )
    )
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None
    async with SessionFactory() as s:
        row = await s.get(AlertModel, alert.id)
        assert row is not None
        row.fired_at = datetime.now(UTC) - timedelta(minutes=minutes)
        await s.commit()
    return alert.id


async def _escalate(branch_id: uuid.UUID) -> int:
    """Corre la pasada de escalado tal y como la corre el worker."""
    session = tracked_session()
    repo = SqlAlchemyAlertRepository(session)
    lifecycle = AlertLifecycle(
        repo, escalation_channels=[WhatsAppEscalationChannel(session)]
    )
    return await lifecycle.escalate_pending({TOMATO.ref: TOMATO})


# --- El caso bueno ----------------------------------------------------------
async def test_it_writes_to_staff_who_already_wrote_to_the_number(
    client, fake_bridge, branch_id: uuid.UUID
) -> None:
    """Sólo se le puede escribir a quien ya escribió: el guardián no se salta ni por dentro."""
    await grant_only([ESCALATION_PERMISSION])
    employee_id = await create_demo_employee(branch_id)
    await subscribe_to_alerts(employee_id)
    await _give_phone(employee_id, "573001112233")
    await create_session_row(branch_id, "inst-alerts")
    # El empleado escribe al número del negocio: eso es lo que lo vuelve contactable.
    await post_inbound(client, "inst-alerts", message_id="e-1", phone="573001112233")
    await link_chat(employee_id, "573001112233")
    fake_bridge.sent.clear()
    await _fire_and_age(branch_id)

    assert await _escalate(branch_id) == 1

    assert len(fake_bridge.sent) == 1
    to_phone, text = fake_bridge.sent[0]
    assert to_phone == "573001112233"
    # El mensaje dice de qué va, no un uuid.
    assert "Tomate" in text
    assert "quedan 2 de 10" in text


# --- Los cuatro límites -----------------------------------------------------
async def test_an_unreachable_employee_gets_nothing_but_it_is_still_recorded(
    client, fake_bridge, branch_id: uuid.UUID
) -> None:
    """El empleado nunca escribió al número. No se le escribe — y no se reintenta jamás."""
    await grant_only([ESCALATION_PERMISSION])
    employee_id = await create_demo_employee(branch_id)
    await subscribe_to_alerts(employee_id)
    await _give_phone(employee_id, "573009998877")
    await create_session_row(branch_id, "inst-alerts")
    alert_id = await _fire_and_age(branch_id)

    escalated = await _escalate(branch_id)

    assert escalated == 1
    assert fake_bridge.sent == []
    # Anotado: si no, el siguiente barrido lo intentaría otra vez, y el siguiente, y el
    # siguiente — cada cinco minutos contra un número que no puede recibirlo.
    repo = SqlAlchemyAlertRepository(tracked_session())
    tenant_id = await demo_tenant_id()
    stored = await repo.get_by_id(tenant_id, alert_id)
    assert stored is not None and stored.last_escalated_at is not None
    assert await _escalate(branch_id) == 0


async def test_a_branch_without_a_number_escalates_to_nobody(
    client, fake_bridge, branch_id: uuid.UUID
) -> None:
    """Un negocio que no usa WhatsApp no puede recibir escalados por WhatsApp."""
    await grant_only([ESCALATION_PERMISSION])
    employee_id = await create_demo_employee(branch_id)
    await subscribe_to_alerts(employee_id)
    await _give_phone(employee_id, "573001112233")
    await _fire_and_age(branch_id)

    assert await _escalate(branch_id) == 1
    assert fake_bridge.sent == []


async def test_staff_without_the_permission_are_not_written_to(
    client, fake_bridge, branch_id: uuid.UUID
) -> None:
    """Se elige por permiso EFECTIVO: quien no puede abrir la pantalla no recibe el aviso."""
    await grant_only(["orders.read"])
    employee_id = await create_demo_employee(branch_id)
    await subscribe_to_alerts(employee_id)
    await _give_phone(employee_id, "573001112233")
    await create_session_row(branch_id, "inst-alerts")
    await post_inbound(client, "inst-alerts", message_id="e-1", phone="573001112233")
    await link_chat(employee_id, "573001112233")
    fake_bridge.sent.clear()
    await _fire_and_age(branch_id)

    await _escalate(branch_id)

    assert fake_bridge.sent == []


async def test_nobody_is_written_to_until_somebody_is_picked(
    client, fake_bridge, branch_id: uuid.UUID
) -> None:
    """La propiedad nueva: tener el permiso YA NO basta.

    Ver el panel de alertas y que le suene el móvil a las once de la noche son cosas
    distintas. Antes estaban atadas al mismo permiso, así que quien debía ver la pantalla
    pero no recibir mensajes no tenía salida. Ahora hay que señalar a la persona.
    """
    await grant_only([ESCALATION_PERMISSION])
    employee_id = await create_demo_employee(branch_id)  # con permiso, sin señalar
    await _give_phone(employee_id, "573001112233")
    await create_session_row(branch_id, "inst-alerts")
    await post_inbound(client, "inst-alerts", message_id="e-1", phone="573001112233")
    await link_chat(employee_id, "573001112233")
    fake_bridge.sent.clear()
    await _fire_and_age(branch_id)

    await _escalate(branch_id)

    assert fake_bridge.sent == []


async def test_unsubscribing_stops_the_messages(
    client, fake_bridge, branch_id: uuid.UUID
) -> None:
    """Y se puede apagar sin perder el acceso al panel — que es el punto entero."""
    await grant_only([ESCALATION_PERMISSION])
    employee_id = await create_demo_employee(branch_id)
    await subscribe_to_alerts(employee_id)
    await _give_phone(employee_id, "573001112233")
    await create_session_row(branch_id, "inst-alerts")
    await post_inbound(client, "inst-alerts", message_id="e-1", phone="573001112233")
    await link_chat(employee_id, "573001112233")
    fake_bridge.sent.clear()
    await subscribe_to_alerts(employee_id, receives=False)
    await _fire_and_age(branch_id)

    await _escalate(branch_id)

    assert fake_bridge.sent == []


async def test_the_escalation_says_the_name_not_the_id(
    client, fake_bridge, branch_id: uuid.UUID
) -> None:
    """El caso que falló de verdad: el hueco de la histéresis.

    El azúcar sube por encima del mínimo pero SIN pasar el colchón. La alerta sigue abierta y
    ya no "dispara", así que el barrido no recoge su nombre — y antes de guardarlo, el aviso
    escalado salía diciendo `5d46e088-ee6a-4b88-…` en vez de "Azúcar".

    Se simula lo que importa: escalar SIN pasarle etiquetas, que es exactamente lo que ocurre
    cuando el sujeto ya no está entre los que disparan.
    """
    await grant_only([ESCALATION_PERMISSION])
    employee_id = await create_demo_employee(branch_id)
    await subscribe_to_alerts(employee_id)
    await create_session_row(branch_id, "inst-alerts")
    await post_inbound(client, "inst-alerts", message_id="e-1", phone="573001112233")
    await link_chat(employee_id, "573001112233")
    fake_bridge.sent.clear()

    tenant_id = await demo_tenant_id()
    repo = SqlAlchemyAlertRepository(tracked_session())
    lifecycle = AlertLifecycle(
        repo, escalation_channels=[WhatsAppEscalationChannel(tracked_session())]
    )
    await lifecycle.save_rule(
        AlertRule(
            tenant_id=tenant_id,
            branch_id=branch_id,
            rule_key=RULE_LOW_STOCK,
            is_enabled=True,
            escalate_to_whatsapp=True,
            escalation_after_minutes=30,
        )
    )
    sugar = Subject(ref="5d46e088-ee6a-4b88-93e1-64864dd6f8e1", label="Azúcar")
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, sugar)
    assert alert is not None and alert.id is not None
    await _age(alert.id, minutes=45)

    # Sin etiquetas: el sujeto ya no dispara, así que nadie las recogió.
    assert await lifecycle.escalate_pending() == 1

    _, text = fake_bridge.sent[0]
    assert "Azúcar" in text
    assert "5d46e088" not in text


async def test_an_alert_from_before_the_label_existed_falls_back_to_the_ref(
    client, fake_bridge, branch_id: uuid.UUID
) -> None:
    """Nada que rellenar hacia atrás: una alerta vieja sale como salía, no con un hueco."""
    await grant_only([ESCALATION_PERMISSION])
    employee_id = await create_demo_employee(branch_id)
    await subscribe_to_alerts(employee_id)
    await create_session_row(branch_id, "inst-alerts")
    await post_inbound(client, "inst-alerts", message_id="e-1", phone="573001112233")
    await link_chat(employee_id, "573001112233")
    fake_bridge.sent.clear()
    alert_id = await _fire_and_age(branch_id)
    async with SessionFactory() as s:
        row = await s.get(AlertModel, alert_id)
        assert row is not None
        row.subject_label = None
        await s.commit()

    await AlertLifecycle(
        SqlAlchemyAlertRepository(tracked_session()),
        escalation_channels=[WhatsAppEscalationChannel(tracked_session())],
    ).escalate_pending()

    _, text = fake_bridge.sent[0]
    assert TOMATO.ref in text


async def test_staff_without_a_phone_are_skipped(
    client, fake_bridge, branch_id: uuid.UUID
) -> None:
    await grant_only([ESCALATION_PERMISSION])
    await subscribe_to_alerts(await create_demo_employee(branch_id))  # sin teléfono
    await create_session_row(branch_id, "inst-alerts")
    await _fire_and_age(branch_id)

    await _escalate(branch_id)

    assert fake_bridge.sent == []


async def test_taking_the_alert_cancels_the_escalation(
    client, fake_bridge, branch_id: uuid.UUID
) -> None:
    await grant_only([ESCALATION_PERMISSION])
    employee_id = await create_demo_employee(branch_id)
    await subscribe_to_alerts(employee_id)
    await _give_phone(employee_id, "573001112233")
    await create_session_row(branch_id, "inst-alerts")
    await post_inbound(client, "inst-alerts", message_id="e-1", phone="573001112233")
    await link_chat(employee_id, "573001112233")
    fake_bridge.sent.clear()
    alert_id = await _fire_and_age(branch_id)

    tenant_id = await demo_tenant_id()
    lifecycle = AlertLifecycle(SqlAlchemyAlertRepository(tracked_session()))
    await lifecycle.acknowledge(tenant_id, alert_id, employee_id)

    assert await _escalate(branch_id) == 0
    assert fake_bridge.sent == []


async def test_it_never_escalates_twice(
    client, fake_bridge, branch_id: uuid.UUID
) -> None:
    await grant_only([ESCALATION_PERMISSION])
    employee_id = await create_demo_employee(branch_id)
    await subscribe_to_alerts(employee_id)
    await _give_phone(employee_id, "573001112233")
    await create_session_row(branch_id, "inst-alerts")
    await post_inbound(client, "inst-alerts", message_id="e-1", phone="573001112233")
    await link_chat(employee_id, "573001112233")
    fake_bridge.sent.clear()
    await _fire_and_age(branch_id)

    await _escalate(branch_id)
    await _escalate(branch_id)
    await _escalate(branch_id)

    # Tres pasadas del worker, un mensaje. `escalated_at` es lo que lo impide.
    assert len(fake_bridge.sent) == 1


async def test_a_bridge_outage_does_not_break_the_pass(
    client, fake_bridge, branch_id: uuid.UUID
) -> None:
    """El puente caído se lleva el aviso, nunca el barrido ni la alerta."""
    await grant_only([ESCALATION_PERMISSION])
    employee_id = await create_demo_employee(branch_id)
    await subscribe_to_alerts(employee_id)
    await _give_phone(employee_id, "573001112233")
    await create_session_row(branch_id, "inst-alerts")
    await post_inbound(client, "inst-alerts", message_id="e-1", phone="573001112233")
    await link_chat(employee_id, "573001112233")
    alert_id = await _fire_and_age(branch_id)
    fake_bridge.fail = True

    assert await _escalate(branch_id) == 1

    tenant_id = await demo_tenant_id()
    repo = SqlAlchemyAlertRepository(tracked_session())
    stored = await repo.get_by_id(tenant_id, alert_id)
    # La alerta sigue abierta y sin tomar: el aviso se perdió, el hecho no.
    assert stored is not None and stored.status == "fired"


# --- Sin canal en absoluto --------------------------------------------------
async def test_the_module_works_with_no_whatsapp_channel_at_all(
    branch_id: uuid.UUID,
) -> None:
    """Sin adaptador enchufado, escalar es sólo anotarlo. El módulo sigue siendo correcto."""
    await _fire_and_age(branch_id)
    lifecycle = AlertLifecycle(SqlAlchemyAlertRepository(tracked_session()))

    assert await lifecycle.escalate_pending() == 1
