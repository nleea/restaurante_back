"""Qué hora es EN EL RESTAURANTE.

Existe por un fallo reportado desde producción: el negocio estaba abierto y el saludo de
WhatsApp mandaba el mensaje de "estamos cerrados". La causa: los horarios se guardan en hora
local de la sede y se comparaban contra UTC. En Colombia (UTC-5) eso corre el reloj cinco
horas y, pasadas las 7 de la tarde, también el día de la semana.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from restaurante.modules.business.application.clock import (
    business_timezone,
    now_local,
    weekday_and_minute,
)
from restaurante.modules.business.domain.hours import HoursWindow, is_open_at


def test_the_default_timezone_is_the_market_we_serve() -> None:
    # Colombia. El día que un negocio no esté aquí, esto se muda al Perfil del negocio.
    assert business_timezone() == ZoneInfo("America/Bogota")


def test_local_time_is_five_hours_behind_utc() -> None:
    local = now_local()
    assert local.utcoffset() is not None
    assert local.utcoffset().total_seconds() == -5 * 3600  # type: ignore[union-attr]


def test_an_open_restaurant_is_not_declared_closed_by_utc() -> None:
    """El caso reportado: 3 de la tarde, abierto, y el sistema decía que no.

    Un lunes de 8:00 a 20:00. A las 15:00 en Riohacha son las 20:00 UTC — justo el minuto
    de cierre—, así que comparar contra UTC contestaba "cerrado" con el local lleno.
    """
    monday_8_to_20 = [HoursWindow(weekday=0, open_minute=8 * 60, close_minute=20 * 60)]
    utc_moment = datetime(2026, 7, 27, 20, 0, tzinfo=UTC)  # lunes 20:00 UTC
    local_moment = utc_moment.astimezone(business_timezone())  # lunes 15:00 local

    # Lo que hacía antes:
    assert not is_open_at(
        monday_8_to_20, utc_moment.weekday(), utc_moment.hour * 60 + utc_moment.minute
    )
    # Lo que hace ahora:
    weekday, minute = weekday_and_minute(local_moment)
    assert is_open_at(monday_8_to_20, weekday, minute)


def test_after_seven_pm_utc_gets_the_weekday_wrong_too() -> None:
    """Lo peor del fallo: no era sólo la hora, era el día — y con él, todo el horario.

    Un negocio que abre lunes por la noche: a las 21:00 del lunes en Colombia son las
    02:00 del MARTES en UTC, así que el sistema consultaba el horario de otro día.
    """
    monday_night = [HoursWindow(weekday=0, open_minute=19 * 60, close_minute=23 * 60)]
    utc_moment = datetime(2026, 7, 28, 2, 0, tzinfo=UTC)  # martes 02:00 UTC
    local_moment = utc_moment.astimezone(business_timezone())  # lunes 21:00 local

    assert utc_moment.weekday() == 1  # martes
    assert local_moment.weekday() == 0  # lunes — el día que de verdad es en el local

    weekday, minute = weekday_and_minute(local_moment)
    assert is_open_at(monday_night, weekday, minute)


def test_weekday_and_minute_speaks_the_language_of_the_hours_table() -> None:
    # 0=lunes … 6=domingo, y minutos desde medianoche: exactamente lo que guarda
    # `operating_hours`, para que no haya conversión en medio que alguien pueda olvidar.
    moment = datetime(2026, 7, 27, 8, 30, tzinfo=business_timezone())
    assert weekday_and_minute(moment) == (0, 510)
