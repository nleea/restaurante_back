"""El API de alertas: ver, tomar y configurar — y quién puede hacer cada cosa.

La separación de permisos es el punto: ver que falta tomate y hacerse cargo es el turno;
decidir umbrales y a quién se le manda un WhatsApp a las once de la noche es el dueño.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from restaurante.modules.alerts.application.use_cases.lifecycle import AlertLifecycle
from restaurante.modules.alerts.domain.entities import (
    RULE_CASH_SESSION_LEFT_OPEN,
    RULE_LOW_STOCK,
)
from restaurante.modules.alerts.domain.ports import Subject
from restaurante.modules.alerts.infrastructure.repositories import (
    SqlAlchemyAlertRepository,
)
from tests.modules.alerts.conftest import demo_tenant_id, tracked_session
from tests.modules.messaging.conftest import grant_only, login

pytestmark = pytest.mark.asyncio

TOMATO = Subject(ref="ing-tomate", label="Tomate", detail="quedan 2 de 10")


async def _fire(branch_id: uuid.UUID) -> uuid.UUID:
    tenant_id = await demo_tenant_id()
    lifecycle = AlertLifecycle(SqlAlchemyAlertRepository(tracked_session()))
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None
    return alert.id


# --- Ver --------------------------------------------------------------------
async def test_an_all_clear_branch_returns_nothing(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    await grant_only(["alerts.read"])
    headers = await login(client)

    resp = await client.get("/alerts", headers=headers, params={"branch_id": str(branch_id)})

    assert resp.status_code == 200, resp.text
    # Vacío es la buena noticia, y es una respuesta, no un error.
    assert resp.json() == []


async def test_open_alerts_are_listed_with_their_subject(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    await _fire(branch_id)
    await grant_only(["alerts.read"])
    headers = await login(client)

    body = (
        await client.get("/alerts", headers=headers, params={"branch_id": str(branch_id)})
    ).json()

    assert len(body) == 1
    assert body[0]["rule_key"] == RULE_LOW_STOCK
    assert body[0]["subject_ref"] == TOMATO.ref
    assert body[0]["status"] == "fired"
    assert body[0]["holder_name"] is None


async def test_the_list_is_scoped_to_the_branch(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    from tests.modules.alerts.conftest import create_branch

    other = await create_branch(f"z{uuid.uuid4().hex[:6]}")
    await _fire(branch_id)
    await grant_only(["alerts.read"])
    headers = await login(client)

    body = (
        await client.get("/alerts", headers=headers, params={"branch_id": str(other)})
    ).json()

    # Cada cocina ve lo suyo: una alerta de otra sede no es información aquí, es ruido.
    assert body == []


# --- Tomar ------------------------------------------------------------------
async def test_acknowledging_records_who(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    from tests.modules.alerts.conftest import create_demo_employee

    alert_id = await _fire(branch_id)
    await create_demo_employee(branch_id)
    await grant_only(["alerts.read"])
    headers = await login(client)

    resp = await client.post(
        f"/alerts/{alert_id}/acknowledge",
        headers=headers,
        params={"branch_id": str(branch_id)},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "acknowledged"
    assert resp.json()["holder_name"] is not None


async def test_the_second_acknowledger_gets_a_conflict_naming_the_holder(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    from tests.modules.alerts.conftest import create_demo_employee

    alert_id = await _fire(branch_id)
    await create_demo_employee(branch_id)
    await grant_only(["alerts.read"])
    headers = await login(client)
    params = {"branch_id": str(branch_id)}
    await client.post(f"/alerts/{alert_id}/acknowledge", headers=headers, params=params)

    resp = await client.post(
        f"/alerts/{alert_id}/acknowledge", headers=headers, params=params
    )

    # Perder la carrera es información: lo útil es que el segundo no repita el trabajo.
    assert resp.status_code == 409, resp.text


async def test_acknowledging_without_being_an_employee_is_refused(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    """Tomar una alerta se atribuye a una PERSONA de esa sucursal, no a un usuario suelto."""
    alert_id = await _fire(branch_id)
    await grant_only(["alerts.read"])
    headers = await login(client)

    resp = await client.post(
        f"/alerts/{alert_id}/acknowledge",
        headers=headers,
        params={"branch_id": str(branch_id)},
    )

    assert resp.status_code == 422, resp.text


# --- Configurar -------------------------------------------------------------
async def test_rules_are_listed_even_when_never_configured(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    await grant_only(["alerts.read"])
    headers = await login(client)

    body = (
        await client.get(
            "/alerts/rules", headers=headers, params={"branch_id": str(branch_id)}
        )
    ).json()

    # Una regla sin fila existe y está apagada: la pantalla tiene que poder encenderla sin
    # que nadie la haya sembrado antes.
    assert {r["rule_key"] for r in body} == {
        RULE_LOW_STOCK,
        "whatsapp_session_down",
        RULE_CASH_SESSION_LEFT_OPEN,
        # El saldo del asistente es una regla más (`assistant-core`): hereda la histéresis
        # en vez de traerse su propio aviso, así que el dueño se entera una vez y no en
        # cada mensaje que le acerca al límite.
        "assistant_quota",
    }
    assert all(r["is_enabled"] is False for r in body)


async def test_saving_a_rule_round_trips(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    await grant_only(["alerts.read", "alerts.manage"])
    headers = await login(client)

    saved = await client.put(
        f"/alerts/rules/{RULE_LOW_STOCK}",
        headers=headers,
        params={"branch_id": str(branch_id)},
        json={
            "is_enabled": True,
            "recovery_buffer": 5,
            "escalation_after_minutes": 15,
            "escalate_to_whatsapp": True,
        },
    )
    assert saved.status_code == 200, saved.text

    body = (
        await client.get(
            "/alerts/rules", headers=headers, params={"branch_id": str(branch_id)}
        )
    ).json()
    low = next(r for r in body if r["rule_key"] == RULE_LOW_STOCK)
    assert low["is_enabled"] is True
    assert low["recovery_buffer"] == 5


async def test_a_zero_recovery_buffer_is_refused_by_the_api(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    """Cero no es una preferencia: es el bug que la histéresis existe para impedir."""
    await grant_only(["alerts.manage"])
    headers = await login(client)

    resp = await client.put(
        f"/alerts/rules/{RULE_LOW_STOCK}",
        headers=headers,
        params={"branch_id": str(branch_id)},
        json={"is_enabled": True, "recovery_buffer": 0},
    )

    assert resp.status_code == 422, resp.text


async def test_an_unknown_rule_key_is_a_404(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    await grant_only(["alerts.manage"])
    headers = await login(client)

    resp = await client.put(
        "/alerts/rules/lo_que_sea",
        headers=headers,
        params={"branch_id": str(branch_id)},
        json={"is_enabled": True},
    )

    assert resp.status_code == 404, resp.text


# --- Permisos ---------------------------------------------------------------
async def test_reading_needs_alerts_read(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    await grant_only(["orders.read"])
    headers = await login(client)

    resp = await client.get("/alerts", headers=headers, params={"branch_id": str(branch_id)})

    assert resp.status_code == 403, resp.text


async def test_reading_does_not_let_anyone_configure(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    """Ver que falta tomate es el turno; decidir umbrales y escalados es el dueño."""
    await grant_only(["alerts.read"])
    headers = await login(client)

    resp = await client.put(
        f"/alerts/rules/{RULE_LOW_STOCK}",
        headers=headers,
        params={"branch_id": str(branch_id)},
        json={"is_enabled": True},
    )

    assert resp.status_code == 403, resp.text


async def test_managing_alone_does_not_grant_the_list(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    await grant_only(["alerts.manage"])
    headers = await login(client)

    resp = await client.get("/alerts", headers=headers, params={"branch_id": str(branch_id)})

    assert resp.status_code == 403, resp.text


# --- Silenciar: la tercera salida --------------------------------------------
async def test_muting_leaves_the_alert_open_and_unowned(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    """Silenciar no es tomar. Si lo fuera, el panel se llenaría de dueños falsos."""
    await grant_only(["alerts.read"])
    headers = await login(client)
    params = {"branch_id": str(branch_id)}
    alert_id = await _fire(branch_id)

    resp = await client.post(f"/alerts/{alert_id}/mute", headers=headers, params=params)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reminders_muted_at"] is not None
    assert body["status"] == "fired"
    assert body["acknowledged_at"] is None
    assert body["acknowledged_by"] is None
    # Y sigue listada: callarla no es esconderla.
    listed = (await client.get("/alerts", headers=headers, params=params)).json()
    assert [a["id"] for a in listed] == [str(alert_id)]


async def test_muting_twice_does_not_break(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    await grant_only(["alerts.read"])
    headers = await login(client)
    params = {"branch_id": str(branch_id)}
    alert_id = await _fire(branch_id)

    first = await client.post(f"/alerts/{alert_id}/mute", headers=headers, params=params)
    second = await client.post(f"/alerts/{alert_id}/mute", headers=headers, params=params)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["reminders_muted_at"] == second.json()["reminders_muted_at"]


async def test_muting_needs_the_alerts_permission(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    alert_id = await _fire(branch_id)
    await grant_only(["messaging.read"])
    headers = await login(client)

    resp = await client.post(
        f"/alerts/{alert_id}/mute", headers=headers, params={"branch_id": str(branch_id)}
    )

    assert resp.status_code == 403


async def test_muting_an_unknown_alert_is_a_404(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    await grant_only(["alerts.read"])
    headers = await login(client)

    resp = await client.post(
        f"/alerts/{uuid.uuid4()}/mute",
        headers=headers,
        params={"branch_id": str(branch_id)},
    )

    assert resp.status_code == 404


# --- El intervalo de recordatorio en la regla --------------------------------
async def test_the_reminder_interval_round_trips(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    await grant_only(["alerts.read", "alerts.manage"])
    headers = await login(client)
    params = {"branch_id": str(branch_id)}

    saved = await client.put(
        f"/alerts/rules/{RULE_LOW_STOCK}",
        headers=headers,
        params=params,
        json={
            "is_enabled": True,
            "recovery_buffer": 10,
            "remind_every_minutes": 15,
            "escalation_after_minutes": 5,
            "escalate_to_whatsapp": False,
        },
    )

    assert saved.status_code == 200, saved.text
    assert saved.json()["remind_every_minutes"] == 15
    listed = (await client.get("/alerts/rules", headers=headers, params=params)).json()
    low = next(r for r in listed if r["rule_key"] == RULE_LOW_STOCK)
    assert low["remind_every_minutes"] == 15


async def test_a_zero_reminder_interval_is_allowed(
    client: AsyncClient, branch_id: uuid.UUID
) -> None:
    """Al revés que el colchón: aquí el cero es una elección legítima, no el bug.

    Es la vía de escape del change — "avisa una vez y no insistas", el comportamiento de antes.
    """
    await grant_only(["alerts.read", "alerts.manage"])
    headers = await login(client)
    params = {"branch_id": str(branch_id)}

    resp = await client.put(
        f"/alerts/rules/{RULE_LOW_STOCK}",
        headers=headers,
        params=params,
        json={
            "is_enabled": True,
            "recovery_buffer": 10,
            "remind_every_minutes": 0,
            "escalation_after_minutes": 5,
            "escalate_to_whatsapp": False,
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["remind_every_minutes"] == 0
