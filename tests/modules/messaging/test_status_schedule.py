"""El horario de los estados. Sin base, sin app, sin reloj.

Dos pruebas de esta suite son las que sostienen el change, y las dos cubren un fallo que ya ocurrió
antes en este repo:

- `test_an_evening_slot_is_due_on_its_local_weekday` es el fallo de `clock.py` —a partir de las
  19:00 en Colombia el día de la semana se corre en UTC—, aplicado a publicar.
- `test_the_emission_key_survives_a_schedule_rewrite` es la razón de que la clave no lleve el id de
  la franja. Si se cae, cualquier guardado republica el día entero.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from restaurante.modules.messaging.domain.status_schedule import (
    MAX_SLOTS_PER_STATUS,
    StatusSlot,
    due_slots,
    emission_detail,
    validate_slots,
)
from restaurante.modules.messaging.infrastructure.models import (
    EMISSION_STATUS,
    EMISSION_STATUS_POST,
    emission_key,
)
from restaurante.shared.domain.errors import ValidationError

ELEVEN = 11 * 60  # 660
SIX_THIRTY_PM = 18 * 60 + 30  # 1110

# Lunes 10 de agosto de 2026 (weekday 0) y el domingo anterior (weekday 6).
MONDAY = date(2026, 8, 10)
SUNDAY = date(2026, 8, 9)


def _weekly(minute: int, *weekdays: int) -> list[StatusSlot]:
    return [StatusSlot(minute=minute, weekday=day) for day in weekdays]


# --- La invariante de la franja ----------------------------------------------
def test_a_slot_with_both_a_weekday_and_a_date_is_refused() -> None:
    with pytest.raises(ValidationError):
        validate_slots([StatusSlot(minute=ELEVEN, weekday=0, on_date=MONDAY)])


def test_a_slot_with_neither_is_refused() -> None:
    with pytest.raises(ValidationError):
        validate_slots([StatusSlot(minute=ELEVEN)])


def test_a_weekly_slot_is_accepted() -> None:
    validate_slots([StatusSlot(minute=ELEVEN, weekday=0)])


def test_a_dated_slot_is_accepted() -> None:
    validate_slots([StatusSlot(minute=ELEVEN, on_date=MONDAY)])


def test_an_hour_outside_the_day_is_refused() -> None:
    with pytest.raises(ValidationError):
        validate_slots([StatusSlot(minute=24 * 60, weekday=0)])


def test_an_unknown_weekday_is_refused() -> None:
    with pytest.raises(ValidationError):
        validate_slots([StatusSlot(minute=ELEVEN, weekday=7)])


def test_two_identical_slots_are_refused() -> None:
    """Publicar las colapsaría, pero una lista con la misma hora dos veces es una pantalla que
    enseña algo que no va a pasar dos veces."""
    with pytest.raises(ValidationError):
        validate_slots(_weekly(ELEVEN, 0) + _weekly(ELEVEN, 0))


def test_too_many_slots_are_refused() -> None:
    with pytest.raises(ValidationError):
        validate_slots(
            [StatusSlot(minute=m, weekday=0) for m in range(MAX_SLOTS_PER_STATUS + 1)]
        )


# --- "Todos los días" y la fecha concreta ------------------------------------
def test_seven_weekday_slots_cover_every_day() -> None:
    """Marcar los siete días ES "todos los días". No hace falta un `kind`."""
    slots = _weekly(ELEVEN, 0, 1, 2, 3, 4, 5, 6)
    validate_slots(slots)

    for offset in range(7):
        day = date(2026, 8, 10 + offset)
        assert due_slots(slots, day, ELEVEN, grace_minutes=30), f"falló {day}"


def test_a_weekly_slot_does_not_fire_on_another_weekday() -> None:
    slots = _weekly(ELEVEN, 0)  # sólo lunes
    assert not due_slots(slots, SUNDAY, ELEVEN, grace_minutes=30)


def test_a_past_dated_slot_never_fires_again() -> None:
    """Un estado de fecha pasada se vuelve inerte solo: el barrido sólo mira lo de HOY, así que no
    hace falta ninguna máquina de estados que lo apague después de publicar."""
    slots = [StatusSlot(minute=ELEVEN, on_date=SUNDAY)]
    assert due_slots(slots, MONDAY, ELEVEN, grace_minutes=30) == []


def test_a_dated_slot_fires_on_its_date() -> None:
    slots = [StatusSlot(minute=SIX_THIRTY_PM, on_date=MONDAY)]
    due = due_slots(slots, MONDAY, SIX_THIRTY_PM, grace_minutes=30)
    assert [d.minute for d in due] == [SIX_THIRTY_PM]


# --- El cruce de medianoche, que es el fallo de clock.py ---------------------
def test_an_evening_slot_is_due_on_its_local_weekday() -> None:
    """Las 20:00 del lunes en UTC-5 vencen el LUNES, no el martes.

    Es el fallo que hizo nacer `clock.py`, aplicado a publicar: a las 20:00 en Bogotá ya es el
    martes en UTC, así que un barrido que derive el día de `datetime.now(UTC)` publicaría el estado
    del martes. Esta prueba pasa por construcción —`due_slots` recibe un `date` local y saca el día
    de él— y está escrita para que quede constancia de que eso es deliberado.
    """
    bogota = ZoneInfo("America/Bogota")
    monday_8pm_local = datetime(2026, 8, 10, 20, 0, tzinfo=bogota)

    assert monday_8pm_local.astimezone(ZoneInfo("UTC")).date() == date(2026, 8, 11)
    assert monday_8pm_local.date() == MONDAY
    assert monday_8pm_local.weekday() == 0  # lunes

    slots = _weekly(20 * 60, 0)  # lunes a las 20:00
    local_date = monday_8pm_local.date()
    now_minute = monday_8pm_local.hour * 60 + monday_8pm_local.minute

    due = due_slots(slots, local_date, now_minute, grace_minutes=30)
    assert [d.minute for d in due] == [20 * 60]


def test_the_weekday_cannot_disagree_with_the_date() -> None:
    """No hay forma de pasar un día de la semana que contradiga la fecha: se deriva de ella."""
    slots = _weekly(ELEVEN, SUNDAY.weekday())
    assert due_slots(slots, SUNDAY, ELEVEN, grace_minutes=30)
    assert not due_slots(slots, MONDAY, ELEVEN, grace_minutes=30)


# --- Vencimiento, gracia y orden --------------------------------------------
def test_a_slot_in_the_future_is_not_due() -> None:
    slots = _weekly(ELEVEN, 0)
    assert due_slots(slots, MONDAY, ELEVEN - 1, grace_minutes=30) == []


def test_a_slot_exactly_now_is_due_and_on_time() -> None:
    due = due_slots(_weekly(ELEVEN, 0), MONDAY, ELEVEN, grace_minutes=30)
    assert due[0].late_by == 0
    assert due[0].within_grace


def test_a_slot_at_the_edge_of_the_grace_window_is_still_on_time() -> None:
    due = due_slots(_weekly(ELEVEN, 0), MONDAY, ELEVEN + 30, grace_minutes=30)
    assert due[0].within_grace


def test_a_slot_past_the_grace_window_is_late() -> None:
    """No desaparece: se devuelve marcada, para que el barrido pueda registrar el omitido en vez de
    callarse."""
    due = due_slots(_weekly(ELEVEN, 0), MONDAY, ELEVEN + 31, grace_minutes=30)
    assert due[0].late_by == 31
    assert not due[0].within_grace


def test_late_by_is_reported_so_the_record_can_say_it() -> None:
    due = due_slots(_weekly(ELEVEN, 0), MONDAY, ELEVEN + 160, grace_minutes=30)
    assert due[0].late_by == 160


def test_two_slots_on_the_same_day_are_two_publications_in_clock_order() -> None:
    slots = [
        StatusSlot(minute=SIX_THIRTY_PM, weekday=0),
        StatusSlot(minute=ELEVEN, weekday=0),
    ]
    due = due_slots(slots, MONDAY, SIX_THIRTY_PM, grace_minutes=24 * 60)
    assert [d.minute for d in due] == [ELEVEN, SIX_THIRTY_PM]


def test_a_weekly_and_a_dated_slot_at_the_same_time_collapse() -> None:
    """UNA publicación, no dos: la clave de emisión es la misma, así que la segunda perdería el
    reclamo de todas formas. Colapsar aquí evita resolver una audiencia para tirarla."""
    slots = [
        StatusSlot(minute=ELEVEN, weekday=MONDAY.weekday()),
        StatusSlot(minute=ELEVEN, on_date=MONDAY),
    ]
    due = due_slots(slots, MONDAY, ELEVEN, grace_minutes=30)
    assert [d.minute for d in due] == [ELEVEN]


def test_no_slots_never_publishes() -> None:
    assert due_slots([], MONDAY, ELEVEN, grace_minutes=30) == []


# --- La clave de emisión ----------------------------------------------------
def test_the_emission_detail_shape() -> None:
    status_id = uuid.UUID("8f3a0000-0000-0000-0000-000000000001")
    assert emission_detail(status_id, MONDAY, ELEVEN) == f"{status_id}:2026-08-10:660"


def test_the_full_key_is_namespaced_apart_from_order_state_notices() -> None:
    """`status:` ya es de los avisos de estado de pedido. Convivir con su misma cara en la misma
    columna es exactamente lo que rompe la auditoría a mano de por qué algo salió dos veces."""
    status_id = uuid.uuid4()
    full = emission_key(EMISSION_STATUS_POST, detail=emission_detail(status_id, MONDAY, ELEVEN))
    assert full == f"status_post:{status_id}:2026-08-10:660"
    assert not full.startswith(f"{EMISSION_STATUS}:")


def test_the_emission_key_survives_a_schedule_rewrite() -> None:
    """La razón entera de que la clave no lleve el id de la franja.

    Las franjas se guardan borrando e reinsertando, así que cada guardado les da un UUID nuevo. Con
    el id dentro, corregir una tilde a las 11:05 hace que el barrido de las 11:06 no encuentre la
    emisión de las 11:00 y publique otra vez.
    """
    status_id = uuid.uuid4()
    before = emission_detail(status_id, MONDAY, ELEVEN)

    # El "guardado": las filas se borran y se reinsertan con ids nuevos. La franja, como valor, es
    # la misma — y la clave, que se construye del valor y no de la fila, no se mueve.
    after = emission_detail(status_id, MONDAY, ELEVEN)

    assert before == after


def test_two_minutes_of_the_same_day_are_two_keys() -> None:
    status_id = uuid.uuid4()
    assert emission_detail(status_id, MONDAY, ELEVEN) != emission_detail(
        status_id, MONDAY, SIX_THIRTY_PM
    )


def test_the_same_slot_on_two_days_are_two_keys() -> None:
    """Es lo que hace que un estado semanal vuelva a publicar mañana."""
    status_id = uuid.uuid4()
    assert emission_detail(status_id, MONDAY, ELEVEN) != emission_detail(
        status_id, SUNDAY, ELEVEN
    )


def test_two_statuses_at_the_same_time_are_two_keys() -> None:
    assert emission_detail(uuid.uuid4(), MONDAY, ELEVEN) != emission_detail(
        uuid.uuid4(), MONDAY, ELEVEN
    )


def test_a_weekly_and_a_dated_slot_share_one_key_format() -> None:
    """La fecha local ya es el discriminante, así que no hay dos formatos que mantener."""
    status_id = uuid.uuid4()
    weekly_fired_on_monday = emission_detail(status_id, MONDAY, ELEVEN)
    dated_for_monday = emission_detail(status_id, MONDAY, ELEVEN)
    assert weekly_fired_on_monday == dated_for_monday
