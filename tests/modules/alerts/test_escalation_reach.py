"""Cuántas personas recibirían un escalado, y por qué las demás no.

Existe porque encender "escalar por WhatsApp" y que no pase nada es indistinguible de que
esté roto. Los tres números del diagnóstico separan las tres causas, y ninguna es evidente
desde la pantalla.

Aquí se prueba además el arreglo del fallo que hacía que esto no funcionara nunca: un
teléfono tecleado con `+` y espacios ahora encuentra a su contacto de WhatsApp.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from restaurante.modules.alerts.infrastructure.whatsapp_escalation import (
    ESCALATION_PERMISSION,
)
from tests.modules.alerts.conftest import (
    create_demo_employee,
    link_chat,
    subscribe_to_alerts,
)
from tests.modules.alerts.test_alert_escalation import _give_phone
from tests.modules.messaging.conftest import (
    create_session_row,
    grant_only,
    login,
    post_inbound,
)

pytestmark = pytest.mark.asyncio


async def _reach(client: AsyncClient, branch_id: uuid.UUID) -> dict[str, object]:
    headers = await login(client)
    resp = await client.get(
        "/alerts/escalation-reach",
        headers=headers,
        params={"branch_id": str(branch_id)},
    )
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


async def test_a_branch_with_nothing_set_up_reaches_nobody(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    await grant_only([ESCALATION_PERMISSION])

    reach = await _reach(client, branch_id)

    # Los tres ceros dicen dónde empezar: primero vincular el número.
    assert reach == {
        "has_session": False,
        "subscribed": 0,
        "with_chat": 0,
        "reachable": 0,
    }


async def test_staff_with_a_phone_count_but_are_not_reachable_yet(
    client: AsyncClient, fake_bridge, branch_id: uuid.UUID
) -> None:
    """El caso que más confunde: todo bien configurado y aun así no llega.

    Falta lo único que no se configura — que la persona escriba al número del negocio.
    """
    await grant_only([ESCALATION_PERMISSION])
    employee_id = await create_demo_employee(branch_id)
    await subscribe_to_alerts(employee_id)
    await _give_phone(employee_id, "573001112233")
    await create_session_row(branch_id, "inst-reach", status="connected")

    reach = await _reach(client, branch_id)

    assert reach["has_session"] is True
    assert reach["subscribed"] == 1
    # Y aquí está la diferencia que la pantalla tiene que explicar.
    assert reach["reachable"] == 0


async def test_writing_to_the_number_makes_the_person_reachable(
    client: AsyncClient, fake_bridge, branch_id: uuid.UUID
) -> None:
    await grant_only([ESCALATION_PERMISSION])
    employee_id = await create_demo_employee(branch_id)
    await subscribe_to_alerts(employee_id)
    await _give_phone(employee_id, "573001112233")
    await create_session_row(branch_id, "inst-reach", status="connected")
    await post_inbound(client, "inst-reach", message_id="r-1", phone="573001112233")
    await link_chat(employee_id, "573001112233")

    reach = await _reach(client, branch_id)

    assert reach["reachable"] == 1


async def test_a_privacy_lid_contact_is_reachable_too(
    client: AsyncClient, fake_bridge, branch_id: uuid.UUID
) -> None:
    """El caso que rompía el emparejamiento por teléfono, y que ahora funciona.

    En modo privacidad WhatsApp manda un `@lid` en vez del número, así que NUNCA sabemos el
    teléfono de esa persona. Emparejando el chat a mano da igual: la dirección con la que se
    le escribe es el `@lid`, y el guardián la reconoce porque escribió con ella.
    """
    await grant_only([ESCALATION_PERMISSION])
    employee_id = await create_demo_employee(branch_id)
    await subscribe_to_alerts(employee_id)
    await create_session_row(branch_id, "inst-reach", status="connected")
    await post_inbound(
        client, "inst-reach", message_id="r-1", phone="196125537607835@lid"
    )
    await link_chat(employee_id, "196125537607835@lid")

    reach = await _reach(client, branch_id)

    # Sin teléfono en ninguna parte, y aun así se le puede escribir.
    assert reach["reachable"] == 1


async def test_staff_without_the_permission_do_not_count(
    client: AsyncClient, fake_bridge, branch_id: uuid.UUID
) -> None:
    await grant_only(["orders.read", ESCALATION_PERMISSION])
    employee_id = await create_demo_employee(branch_id)
    await subscribe_to_alerts(employee_id)
    await _give_phone(employee_id, "573001112233")
    await create_session_row(branch_id, "inst-reach", status="connected")
    # El propio usuario que consulta SÍ tiene el permiso, así que cuenta; lo que se
    # comprueba es que el número sale de los permisos y no de "cualquier empleado".
    reach = await _reach(client, branch_id)
    assert reach["subscribed"] == 1


async def test_a_disconnected_number_is_reported_as_such(
    client: AsyncClient, fake_bridge, branch_id: uuid.UUID
) -> None:
    await grant_only([ESCALATION_PERMISSION])
    await create_session_row(branch_id, "inst-reach", status="disconnected")

    reach = await _reach(client, branch_id)

    # Vinculado pero sin escanear el QR no sirve: el aviso no saldría igual.
    assert reach["has_session"] is False


async def test_the_diagnostic_needs_permission(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    await grant_only(["orders.read"])
    headers = await login(client)

    resp = await client.get(
        "/alerts/escalation-reach",
        headers=headers,
        params={"branch_id": str(branch_id)},
    )

    assert resp.status_code == 403, resp.text
