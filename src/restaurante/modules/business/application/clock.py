"""Qué hora es EN EL RESTAURANTE.

Un solo sitio, y existe por un fallo concreto: los horarios de atención se guardan como
minutos desde medianoche en hora **local de la sede**, pero el saludo automático los
comparaba contra `datetime.now(UTC)` y la carta pública contra `datetime.now()` —la hora del
servidor, que en un contenedor es UTC—. En Colombia (UTC-5) eso significa que a las 3 de la
tarde el sistema creía que eran las 20:00 y le decía al cliente que estaba cerrado; y a
partir de las 7 de la tarde, cuando UTC cruza la medianoche, hasta el DÍA de la semana
estaba corrido, así que consultaba el horario del día siguiente.

La regla, de una vez: **cualquier cosa que se compare con `operating_hours` pasa por aquí.**
Lo que se guarda en la base de datos sigue siendo UTC (`fired_at`, `sent_at`, tokens); esto
es sólo para responder "¿estamos abiertos?" y "¿cuándo abrimos?".
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from restaurante.shared.config import get_settings


def business_timezone() -> ZoneInfo:
    """La zona configurada, o UTC si el nombre no existe en el sistema.

    Un nombre mal escrito no puede tumbar la carta pública ni el saludo: se degrada a UTC,
    que es lo que hacía antes de este arreglo, en vez de reventar.
    """
    try:
        return ZoneInfo(get_settings().timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def now_local() -> datetime:
    """El instante actual en la zona del negocio, con zona incluida."""
    return datetime.now(business_timezone())


def weekday_and_minute(moment: datetime | None = None) -> tuple[int, int]:
    """`(weekday, minute)` tal y como los entiende `hours.py`.

    `weekday` es 0=lunes … 6=domingo (el de Python, que ya coincide con el de la tabla) y
    `minute` son los minutos desde la medianoche local.
    """
    at = moment or now_local()
    return at.weekday(), at.hour * 60 + at.minute
