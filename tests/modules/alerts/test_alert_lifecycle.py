"""El ciclo de vida de una alerta.

Lo que se prueba aquí no es "¿detecta?" sino "¿se calla?". Una implementación que dispara
bien y no deja de hablar es peor que ninguna: alguien la silencia y la siguiente alerta de
verdad no la ve nadie.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from restaurante.modules.alerts.application.use_cases.lifecycle import (
    NOTIFY_ESCALATED,
    NOTIFY_FIRED,
    NOTIFY_REMINDER,
    AlertLifecycle,
)
from restaurante.modules.alerts.domain.entities import (
    ALERT_ACKNOWLEDGED,
    ALERT_RESOLVED,
    RULE_LOW_STOCK,
    AlertRule,
)
from restaurante.modules.alerts.domain.errors import AlreadyAcknowledgedError
from restaurante.modules.alerts.domain.ports import Subject
from restaurante.modules.alerts.infrastructure.models import AlertModel
from restaurante.modules.alerts.infrastructure.repositories import (
    SqlAlchemyAlertRepository,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.domain.errors import NotFoundError, ValidationError
from tests.modules.alerts.conftest import (
    RecordingChannel,
    create_branch,
    create_employee,
    demo_tenant_id,
    tracked_session,
)

pytestmark = pytest.mark.asyncio

TOMATO = Subject(ref="ing-tomate", label="Tomate", detail="quedan 2 kg de 10")


def _lifecycle(
    channel: RecordingChannel | None = None,
    escalation: RecordingChannel | None = None,
) -> tuple[AlertLifecycle, SqlAlchemyAlertRepository]:
    """El ciclo de vida sobre una sesión real: lo que se prueba ES la constraint de la BD.

    Un doble del repositorio validaría el doble; aquí el índice único parcial es el sujeto.
    """
    repo = SqlAlchemyAlertRepository(tracked_session())
    return (
        AlertLifecycle(
            repo,
            channels=[channel] if channel else [],
            escalation_channels=[escalation] if escalation else [],
        ),
        repo,
    )


# --- Disparar una vez -------------------------------------------------------
async def test_fires_once_and_notifies_once(branch_id: uuid.UUID) -> None:
    tenant_id = await demo_tenant_id()
    channel = RecordingChannel()
    lifecycle, repo = _lifecycle(channel)

    first = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    second = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)

    assert first is not None
    # La condición sigue siendo cierta, pero ya lo dijimos. Segundo evaluador: silencio.
    assert second is None
    assert channel.sent == [(RULE_LOW_STOCK, "ing-tomate", NOTIFY_FIRED)]
    assert len(await repo.list_open(tenant_id, branch_id)) == 1


async def test_a_persisting_condition_never_re_fires(branch_id: uuid.UUID) -> None:
    """El tomate sigue bajo diez evaluaciones seguidas. Un aviso, no diez."""
    tenant_id = await demo_tenant_id()
    channel = RecordingChannel()
    lifecycle, _ = _lifecycle(channel)

    for _ in range(10):
        await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)

    assert len(channel.sent) == 1


async def test_two_subjects_of_one_rule_are_independent(branch_id: uuid.UUID) -> None:
    tenant_id = await demo_tenant_id()
    channel = RecordingChannel()
    lifecycle, _ = _lifecycle(channel)

    await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    await lifecycle.fire(
        tenant_id, branch_id, RULE_LOW_STOCK, Subject(ref="ing-queso", label="Queso")
    )

    # Quedarse sin tomate no puede tapar que también falta queso.
    assert len(channel.sent) == 2


async def test_the_same_subject_in_two_branches_is_two_alerts(
    branch_id: uuid.UUID,
) -> None:
    tenant_id = await demo_tenant_id()
    other = await create_branch(f"o{uuid.uuid4().hex[:6]}")
    channel = RecordingChannel()
    lifecycle, _ = _lifecycle(channel)

    await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    await lifecycle.fire(tenant_id, other, RULE_LOW_STOCK, TOMATO)

    # Cada cocina tiene su propia despensa; una no habla por la otra.
    assert len(channel.sent) == 2


# --- Re-armar ---------------------------------------------------------------
async def test_resolving_re_arms_the_subject(branch_id: uuid.UUID) -> None:
    """Cerrar es lo que devuelve la voz. Sin esto, un sujeto se queda mudo para siempre."""
    tenant_id = await demo_tenant_id()
    channel = RecordingChannel()
    lifecycle, _ = _lifecycle(channel)

    await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    closed = await lifecycle.resolve_cleared(
        tenant_id, branch_id, RULE_LOW_STOCK, [TOMATO.ref]
    )
    assert closed == 1

    # Se vuelve a acabar el tomate otra semana: eso SÍ es un episodio nuevo.
    again = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert again is not None
    assert len(channel.sent) == 2


async def test_a_resolved_alert_is_kept_not_deleted(branch_id: uuid.UUID) -> None:
    tenant_id = await demo_tenant_id()
    lifecycle, repo = _lifecycle()

    await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    await lifecycle.resolve_cleared(tenant_id, branch_id, RULE_LOW_STOCK, [TOMATO.ref])
    await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)

    async with SessionFactory() as session:
        stmt = select(AlertModel).where(
            AlertModel.branch_id == branch_id, AlertModel.subject_ref == TOMATO.ref
        )
        rows = (await session.execute(stmt)).scalars().all()

    # Dos episodios, dos filas: "cuántas veces nos quedamos sin tomate" tiene que ser
    # contestable, y por eso el índice único es PARCIAL sobre las abiertas.
    assert len(rows) == 2
    assert {row.status for row in rows} == {ALERT_RESOLVED, "fired"}


async def test_resolving_something_that_never_fired_is_harmless(
    branch_id: uuid.UUID,
) -> None:
    tenant_id = await demo_tenant_id()
    lifecycle, _ = _lifecycle()
    assert (
        await lifecycle.resolve_cleared(
            tenant_id, branch_id, RULE_LOW_STOCK, ["nada-de-nada"]
        )
        == 0
    )


# --- Tomarla ----------------------------------------------------------------
async def test_acknowledgement_is_attributed(branch_id: uuid.UUID) -> None:
    tenant_id = await demo_tenant_id()
    lifecycle, _ = _lifecycle()
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None
    employee_id = await create_employee(branch_id, "Ana")

    taken = await lifecycle.acknowledge(tenant_id, alert.id, employee_id)

    assert taken.status == ALERT_ACKNOWLEDGED
    assert taken.acknowledged_by == employee_id
    assert taken.acknowledged_at is not None


async def test_the_second_acknowledger_is_told_who_holds_it(
    branch_id: uuid.UUID,
) -> None:
    tenant_id = await demo_tenant_id()
    lifecycle, _ = _lifecycle()
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None
    await lifecycle.acknowledge(tenant_id, alert.id, await create_employee(branch_id, "Ana"))

    # Perder la carrera es información, no un fallo: lo útil es que el segundo no repita
    # el trabajo. Misma forma que tomar una conversación en el inbox compartido.
    with pytest.raises(AlreadyAcknowledgedError):
        await lifecycle.acknowledge(tenant_id, alert.id, await create_employee(branch_id, "Bruno"))


async def test_acknowledging_something_that_does_not_exist_says_so(
    branch_id: uuid.UUID,
) -> None:
    tenant_id = await demo_tenant_id()
    lifecycle, _ = _lifecycle()
    # "No existe" y "ya la tienen" mandan a hacer cosas distintas, así que se dicen distinto.
    with pytest.raises(NotFoundError):
        employee_id = await create_employee(branch_id, "Ana")
        await lifecycle.acknowledge(tenant_id, uuid.uuid4(), employee_id)


async def test_an_acknowledged_alert_still_blocks_a_new_one(
    branch_id: uuid.UUID,
) -> None:
    """Tomarla no la resuelve: el tomate sigue bajo y no debe volver a avisar."""
    tenant_id = await demo_tenant_id()
    channel = RecordingChannel()
    lifecycle, _ = _lifecycle(channel)
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None
    await lifecycle.acknowledge(tenant_id, alert.id, await create_employee(branch_id, "Ana"))

    assert await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO) is None
    assert len(channel.sent) == 1


# --- El canal no es la alerta -----------------------------------------------
async def test_a_broken_channel_does_not_lose_the_alert(branch_id: uuid.UUID) -> None:
    tenant_id = await demo_tenant_id()
    broken = RecordingChannel(fail=True)
    lifecycle, repo = _lifecycle(broken)

    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)

    # El aviso se pierde; el hecho no. Y el barrido siguiente NO lo repite, porque la
    # alerta sigue abierta: preferimos un aviso perdido a cuarenta repetidos.
    assert alert is not None
    assert len(await repo.list_open(tenant_id, branch_id)) == 1


async def test_it_works_with_no_channels_at_all(branch_id: uuid.UUID) -> None:
    """Con WhatsApp ausente y sin tiempo real, el módulo sigue siendo correcto."""
    tenant_id = await demo_tenant_id()
    lifecycle, repo = _lifecycle()
    assert await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO) is not None
    assert len(await repo.list_open(tenant_id, branch_id)) == 1


# --- Escalado ---------------------------------------------------------------
def _rule(tenant_id: uuid.UUID, branch_id: uuid.UUID, **over: object) -> AlertRule:
    """Una regla encendida que escala a WhatsApp; los tests cambian lo que les interesa."""
    fields: dict[str, object] = {
        "is_enabled": True,
        "escalate_to_whatsapp": True,
        "escalation_after_minutes": 30,
        **over,
    }
    return AlertRule(
        tenant_id=tenant_id,
        branch_id=branch_id,
        rule_key=RULE_LOW_STOCK,
        **fields,  # type: ignore[arg-type]
    )


async def _age_alert(alert_id: uuid.UUID, minutes: int) -> None:
    """Envejece la alerta en la base de datos: probar el plazo esperando no es una prueba."""
    async with SessionFactory() as session:
        row = await session.get(AlertModel, alert_id)
        assert row is not None
        row.fired_at = datetime.now(UTC) - timedelta(minutes=minutes)
        await session.commit()


async def test_escalation_happens_once_past_the_delay(branch_id: uuid.UUID) -> None:
    tenant_id = await demo_tenant_id()
    escalation = RecordingChannel()
    lifecycle, repo = _lifecycle(escalation=escalation)
    await lifecycle.save_rule(_rule(tenant_id, branch_id))
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None
    await _age_alert(alert.id, minutes=45)

    assert await lifecycle.escalate_pending() == 1
    # Una segunda pasada no la escala otra vez: `escalated_at` es lo que lo impide.
    assert await lifecycle.escalate_pending() == 0
    assert escalation.sent == [(RULE_LOW_STOCK, TOMATO.ref, NOTIFY_ESCALATED)]


async def test_taking_it_prevents_the_escalation(branch_id: uuid.UUID) -> None:
    """Tomarla es exactamente lo que evita gastar un WhatsApp en ella."""
    tenant_id = await demo_tenant_id()
    escalation = RecordingChannel()
    lifecycle, _ = _lifecycle(escalation=escalation)
    await lifecycle.save_rule(_rule(tenant_id, branch_id))
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None
    await _age_alert(alert.id, minutes=45)
    await lifecycle.acknowledge(tenant_id, alert.id, await create_employee(branch_id, "Ana"))

    assert await lifecycle.escalate_pending() == 0
    assert escalation.sent == []


async def test_nothing_escalates_before_its_delay(branch_id: uuid.UUID) -> None:
    tenant_id = await demo_tenant_id()
    escalation = RecordingChannel()
    lifecycle, _ = _lifecycle(escalation=escalation)
    await lifecycle.save_rule(_rule(tenant_id, branch_id))
    await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)

    assert await lifecycle.escalate_pending() == 0


async def test_a_rule_that_does_not_escalate_never_spends_a_message(
    branch_id: uuid.UUID,
) -> None:
    tenant_id = await demo_tenant_id()
    escalation = RecordingChannel()
    lifecycle, _ = _lifecycle(escalation=escalation)
    await lifecycle.save_rule(
        _rule(tenant_id, branch_id, escalate_to_whatsapp=False)
    )
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None
    await _age_alert(alert.id, minutes=999)

    assert await lifecycle.escalate_pending() == 0


async def test_an_unreachable_escalation_is_still_recorded(
    branch_id: uuid.UUID,
) -> None:
    """El envío falla; el escalado queda anotado igual — si no, se reintentaría cada pasada."""
    tenant_id = await demo_tenant_id()
    broken = RecordingChannel(fail=True)
    lifecycle, repo = _lifecycle(escalation=broken)
    await lifecycle.save_rule(_rule(tenant_id, branch_id))
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None
    await _age_alert(alert.id, minutes=45)

    assert await lifecycle.escalate_pending() == 1
    assert await lifecycle.escalate_pending() == 0
    stored = await repo.get_by_id(tenant_id, alert.id)
    assert stored is not None and stored.last_escalated_at is not None


# --- Configuración ----------------------------------------------------------
async def test_a_zero_recovery_buffer_is_rejected(branch_id: uuid.UUID) -> None:
    """Cero no es una preferencia: es el bug que la histéresis existe para impedir."""
    tenant_id = await demo_tenant_id()
    lifecycle, _ = _lifecycle()

    with pytest.raises(ValidationError):
        await lifecycle.save_rule(_rule(tenant_id, branch_id, recovery_buffer=0))
    with pytest.raises(ValidationError):
        await lifecycle.save_rule(_rule(tenant_id, branch_id, recovery_buffer=-1))


async def test_a_zero_escalation_delay_is_rejected(branch_id: uuid.UUID) -> None:
    tenant_id = await demo_tenant_id()
    lifecycle, _ = _lifecycle()
    with pytest.raises(ValidationError):
        await lifecycle.save_rule(
            _rule(tenant_id, branch_id, escalation_after_minutes=0)
        )


async def test_rules_are_per_branch(branch_id: uuid.UUID) -> None:
    tenant_id = await demo_tenant_id()
    other = await create_branch(f"p{uuid.uuid4().hex[:6]}")
    lifecycle, repo = _lifecycle()

    await lifecycle.save_rule(_rule(tenant_id, branch_id))

    # Encenderla en una sede no la enciende en las demás.
    assert await repo.get_rule(tenant_id, other, RULE_LOW_STOCK) is None
    enabled = await repo.list_enabled_rules()
    assert [r.branch_id for r in enabled if r.branch_id == branch_id]


async def test_saving_a_rule_twice_updates_it(branch_id: uuid.UUID) -> None:
    tenant_id = await demo_tenant_id()
    lifecycle, repo = _lifecycle()
    await lifecycle.save_rule(_rule(tenant_id, branch_id, recovery_buffer=2))
    await lifecycle.save_rule(_rule(tenant_id, branch_id, recovery_buffer=5))

    stored = await repo.get_rule(tenant_id, branch_id, RULE_LOW_STOCK)
    assert stored is not None and stored.recovery_buffer == 5


# --- Recordatorios y las tres salidas ----------------------------------------
# Aquí está el change. El módulo avisaba UNA vez y callaba para siempre, así que una alerta que
# saltaba cuando nadie miraba la pantalla se perdía entera. Repetir sólo es sostenible porque
# ahora callar cuesta un toque, y por eso lo que se prueba son las TRES salidas: si alguna deja
# de cortar los recordatorios, esto se convierte en la máquina de ruido que el módulo temía.
async def _age_notification(alert_id: uuid.UUID, minutes: int) -> None:
    """Envejece el último aviso. Es lo que hace que el recordatorio esté "debido"."""
    async with SessionFactory() as session:
        row = await session.get(AlertModel, alert_id)
        assert row is not None
        row.last_notified_at = datetime.now(UTC) - timedelta(minutes=minutes)
        await session.commit()


async def _fire_with_rule(
    branch_id: uuid.UUID, channel: RecordingChannel, **rule_over: object
) -> tuple[AlertLifecycle, uuid.UUID, uuid.UUID]:
    tenant_id = await demo_tenant_id()
    lifecycle, _ = _lifecycle(channel)
    await lifecycle.save_rule(_rule(tenant_id, branch_id, **rule_over))
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None
    return lifecycle, tenant_id, alert.id


async def test_an_untouched_alert_is_reminded(branch_id: uuid.UUID) -> None:
    channel = RecordingChannel()
    lifecycle, _, alert_id = await _fire_with_rule(branch_id, channel)
    await _age_notification(alert_id, minutes=10)

    assert await lifecycle.remind_pending() == 1

    # El recordatorio se distingue del primer aviso: con el mismo texto se leería como un
    # problema NUEVO, y a la tercera vez el panel parecería contar cuatro alertas donde hay una.
    assert channel.sent == [
        (RULE_LOW_STOCK, "ing-tomate", NOTIFY_FIRED),
        (RULE_LOW_STOCK, "ing-tomate", NOTIFY_REMINDER),
    ]


async def test_firing_counts_as_a_notification(branch_id: uuid.UUID) -> None:
    """Sin esto el primer recordatorio saldría en el barrido siguiente, no un intervalo después."""
    channel = RecordingChannel()
    lifecycle, _, _ = await _fire_with_rule(branch_id, channel)

    assert await lifecycle.remind_pending() == 0


async def test_a_zero_interval_never_reminds(branch_id: uuid.UUID) -> None:
    """`0` es la vía de escape: reproduce exactamente el comportamiento anterior al change."""
    channel = RecordingChannel()
    lifecycle, _, alert_id = await _fire_with_rule(
        branch_id, channel, remind_every_minutes=0
    )
    await _age_notification(alert_id, minutes=999)

    assert await lifecycle.remind_pending() == 0


async def test_reminding_does_not_create_a_second_alert(branch_id: uuid.UUID) -> None:
    channel = RecordingChannel()
    lifecycle, tenant_id, alert_id = await _fire_with_rule(branch_id, channel)
    async with SessionFactory() as session:
        before = (await session.get(AlertModel, alert_id)).fired_at  # type: ignore[union-attr]
    await _age_notification(alert_id, minutes=10)

    await lifecycle.remind_pending()

    open_alerts = await SqlAlchemyAlertRepository(tracked_session()).list_open(
        tenant_id, branch_id
    )
    assert len(open_alerts) == 1
    async with SessionFactory() as session:
        assert (await session.get(AlertModel, alert_id)).fired_at == before  # type: ignore[union-attr]


# --- Salida 1: tomarla -------------------------------------------------------
async def test_acknowledging_stops_the_reminders(branch_id: uuid.UUID) -> None:
    channel = RecordingChannel()
    lifecycle, tenant_id, alert_id = await _fire_with_rule(branch_id, channel)
    await lifecycle.acknowledge(tenant_id, alert_id, await create_employee(branch_id, "Ana"))
    await _age_notification(alert_id, minutes=999)

    assert await lifecycle.remind_pending() == 0


# --- Salida 2: resolverse ----------------------------------------------------
async def test_resolving_stops_the_reminders(branch_id: uuid.UUID) -> None:
    channel = RecordingChannel()
    lifecycle, tenant_id, alert_id = await _fire_with_rule(branch_id, channel)
    await lifecycle.resolve_cleared(tenant_id, branch_id, RULE_LOW_STOCK, ["ing-tomate"])
    await _age_notification(alert_id, minutes=999)

    assert await lifecycle.remind_pending() == 0


# --- Salida 3: silenciar -----------------------------------------------------
async def test_muting_stops_the_reminders(branch_id: uuid.UUID) -> None:
    channel = RecordingChannel()
    lifecycle, tenant_id, alert_id = await _fire_with_rule(branch_id, channel)
    await lifecycle.mute_reminders(tenant_id, alert_id)
    await _age_notification(alert_id, minutes=999)

    assert await lifecycle.remind_pending() == 0


async def test_muting_is_not_taking(branch_id: uuid.UUID) -> None:
    """La diferencia que sostiene el panel: silenciar no afirma que nadie se haga cargo.

    Si callar exigiera tomar, el registro de quién atiende qué se llenaría de mentiras.
    """
    channel = RecordingChannel()
    lifecycle, tenant_id, alert_id = await _fire_with_rule(branch_id, channel)

    muted = await lifecycle.mute_reminders(tenant_id, alert_id)

    assert muted.reminders_muted_at is not None
    assert muted.status == "fired"  # sigue abierta, sin dueño
    assert muted.acknowledged_at is None
    assert muted.acknowledged_by is None
    # Y sigue en el panel: silenciar no la esconde.
    assert len(await SqlAlchemyAlertRepository(tracked_session()).list_open(
        tenant_id, branch_id
    )) == 1


async def test_muting_twice_is_idempotent(branch_id: uuid.UUID) -> None:
    """Quien vuelve a pulsar el botón merece ver el estado, no un error."""
    channel = RecordingChannel()
    lifecycle, tenant_id, alert_id = await _fire_with_rule(branch_id, channel)

    first = await lifecycle.mute_reminders(tenant_id, alert_id)
    second = await lifecycle.mute_reminders(tenant_id, alert_id)

    assert first.reminders_muted_at == second.reminders_muted_at


async def test_muting_one_alert_leaves_its_siblings_alone(branch_id: uuid.UUID) -> None:
    """"Deja de avisarme de las servilletas" no puede significar "de que falta stock"."""
    tenant_id = await demo_tenant_id()
    channel = RecordingChannel()
    lifecycle, _ = _lifecycle(channel)
    await lifecycle.save_rule(_rule(tenant_id, branch_id))
    cheese = Subject(ref="ing-queso", label="Queso")
    first = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    second = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, cheese)
    assert first is not None and first.id is not None
    assert second is not None and second.id is not None
    await lifecycle.mute_reminders(tenant_id, first.id)
    await _age_notification(first.id, minutes=10)
    await _age_notification(second.id, minutes=10)

    assert await lifecycle.remind_pending() == 1
    assert (RULE_LOW_STOCK, "ing-queso", NOTIFY_REMINDER) in channel.sent


async def test_the_silence_dies_with_the_alert(branch_id: uuid.UUID) -> None:
    """Un silencio que sobrevive a la resolución es un olvido que apaga la alerta de mañana."""
    channel = RecordingChannel()
    lifecycle, tenant_id, alert_id = await _fire_with_rule(branch_id, channel)
    await lifecycle.mute_reminders(tenant_id, alert_id)
    await lifecycle.resolve_cleared(tenant_id, branch_id, RULE_LOW_STOCK, ["ing-tomate"])

    reborn = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)

    assert reborn is not None and reborn.id is not None
    assert reborn.reminders_muted_at is None
    await _age_notification(reborn.id, minutes=10)
    assert await lifecycle.remind_pending() == 1


# --- WhatsApp: primero pronto, luego cada 4 horas -----------------------------
# Los dos relojes son la decisión de producto de este change. El panel puede repetir cada cinco
# minutos porque no cuesta nada; el teléfono no: quien paga un mensaje de más no es el dueño, es
# el número, y bloquearlo deja mudo todo el WhatsApp del restaurante, pedidos incluidos.
async def _age_escalation(alert_id: uuid.UUID, hours: float) -> None:
    async with SessionFactory() as session:
        row = await session.get(AlertModel, alert_id)
        assert row is not None
        row.last_escalated_at = datetime.now(UTC) - timedelta(hours=hours)
        await session.commit()


async def test_the_first_whatsapp_leaves_on_the_rule_delay(branch_id: uuid.UUID) -> None:
    tenant_id = await demo_tenant_id()
    escalation = RecordingChannel()
    lifecycle, _ = _lifecycle(escalation=escalation)
    await lifecycle.save_rule(_rule(tenant_id, branch_id, escalation_after_minutes=5))
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None

    assert await lifecycle.escalate_pending() == 0  # a los 0 minutos, nada
    await _age_alert(alert.id, minutes=6)
    assert await lifecycle.escalate_pending() == 1  # a los 6, sale


async def test_whatsapp_does_not_repeat_before_four_hours(branch_id: uuid.UUID) -> None:
    """Dos horas después NO sale nada. Es el número lo que se protege, no la paciencia de nadie."""
    tenant_id = await demo_tenant_id()
    escalation = RecordingChannel()
    lifecycle, _ = _lifecycle(escalation=escalation)
    await lifecycle.save_rule(_rule(tenant_id, branch_id, escalation_after_minutes=5))
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None
    await _age_alert(alert.id, minutes=6)
    await lifecycle.escalate_pending()

    await _age_escalation(alert.id, hours=2)

    assert await lifecycle.escalate_pending() == 0
    assert len(escalation.sent) == 1


async def test_whatsapp_repeats_after_four_hours(branch_id: uuid.UUID) -> None:
    tenant_id = await demo_tenant_id()
    escalation = RecordingChannel()
    lifecycle, _ = _lifecycle(escalation=escalation)
    await lifecycle.save_rule(_rule(tenant_id, branch_id, escalation_after_minutes=5))
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None
    await _age_alert(alert.id, minutes=6)
    await lifecycle.escalate_pending()

    await _age_escalation(alert.id, hours=4.1)

    assert await lifecycle.escalate_pending() == 1
    assert len(escalation.sent) == 2


async def test_a_day_of_being_ignored_costs_exactly_six_messages(
    branch_id: uuid.UUID,
) -> None:
    """El techo. 24 h ÷ 4 h = 6, y ni uno más: es lo que separa insistir de que te bloqueen."""
    tenant_id = await demo_tenant_id()
    escalation = RecordingChannel()
    lifecycle, _ = _lifecycle(escalation=escalation)
    await lifecycle.save_rule(_rule(tenant_id, branch_id, escalation_after_minutes=5))
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None
    await _age_alert(alert.id, minutes=6)

    # Un día entero, mirando cada 5 minutos como hace el barrido de verdad. El reloj se simula
    # envejeciendo `last_escalated_at`: cuánto hace que salió el último, en minutos simulados.
    sent = 0
    last_escalation_min: int | None = None
    for minute in range(0, 24 * 60, 5):
        if last_escalation_min is not None:
            await _age_escalation(alert.id, hours=(minute - last_escalation_min) / 60)
        if await lifecycle.escalate_pending():
            sent += 1
            last_escalation_min = minute

    assert sent == 6
    assert len(escalation.sent) == 6


async def test_muting_stops_the_whatsapp_too(branch_id: uuid.UUID) -> None:
    """Silenciar es una de las TRES salidas, no un botón del panel: corta también el teléfono."""
    tenant_id = await demo_tenant_id()
    escalation = RecordingChannel()
    lifecycle, _ = _lifecycle(escalation=escalation)
    await lifecycle.save_rule(_rule(tenant_id, branch_id, escalation_after_minutes=5))
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None
    await _age_alert(alert.id, minutes=6)
    await lifecycle.mute_reminders(tenant_id, alert.id)

    assert await lifecycle.escalate_pending() == 0
    assert escalation.sent == []


async def test_reminders_never_reach_the_escalation_channel(
    branch_id: uuid.UUID,
) -> None:
    """Un recordatorio del panel no puede provocar un mensaje. Es la regla dura del change."""
    tenant_id = await demo_tenant_id()
    panel, escalation = RecordingChannel(), RecordingChannel()
    lifecycle, _ = _lifecycle(panel, escalation)
    await lifecycle.save_rule(_rule(tenant_id, branch_id))
    alert = await lifecycle.fire(tenant_id, branch_id, RULE_LOW_STOCK, TOMATO)
    assert alert is not None and alert.id is not None

    for _ in range(20):
        await _age_notification(alert.id, minutes=10)
        await lifecycle.remind_pending()

    assert len(panel.sent) == 21  # el disparo + 20 recordatorios
    assert escalation.sent == []


async def test_reminders_work_with_no_escalation_channel(branch_id: uuid.UUID) -> None:
    """El módulo funciona con WhatsApp ausente; los recordatorios del panel no dependen de él."""
    channel = RecordingChannel()
    lifecycle, _, alert_id = await _fire_with_rule(branch_id, channel)
    await _age_notification(alert_id, minutes=10)

    assert await lifecycle.remind_pending() == 1
