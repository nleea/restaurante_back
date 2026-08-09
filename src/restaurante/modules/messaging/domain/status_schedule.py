"""Cuándo toca publicar un estado, y la clave que impide publicarlo dos veces.

Funciones puras: sin base de datos, sin red y **sin reloj**. Mismo criterio que `templates.py`,
`faq.py` y `quick_reply.py`. Quien llama trae el momento; aquí no se pregunta la hora.

Tres decisiones sostienen el fichero, y las tres son contraintuitivas.

1. **Una franja es un día de la semana O una fecha, nunca las dos.** Con eso "todos los días a las
   once" (siete franjas de `weekday`) y "el 15 a las seis" (una de `on_date`) son la misma tabla, la
   misma consulta y la misma clave. Y por eso **no existe un campo `kind`** en el estado: un
   `kind` sería un segundo sitio donde se decide el mismo hecho, y podría contradecir a sus propias
   franjas (`kind='once'` con siete `weekday`: ¿quién gana?). Las franjas SON el horario.

2. **El día lo manda la FECHA, no un `weekday` que venga por separado.** `due_slots` recibe un
   `date` y deriva el día de la semana de él. Es imposible que los dos discrepen, y es imposible
   pasarle un instante UTC y que "parezca funcionar": hay que descomponerlo a propósito. Ese es
   justo el fallo que hizo nacer `business/application/clock.py` — a partir de las 19:00 en
   Colombia, UTC ya cruzó la medianoche y el día de la semana está corrido, así que un barrido en
   UTC publica el horario de MAÑANA.

3. **La clave de emisión no lleva el id de la franja.** Ver `emission_key`. Es la decisión menos
   obvia del módulo y la que evita un reenvío masivo.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from restaurante.shared.domain.errors import ValidationError

#: Minutos que tiene un día. Un minuto válido está en `[0, 1440)`.
MINUTES_PER_DAY = 24 * 60

#: Días de la semana, 0=lunes … 6=domingo. El mismo convenio que `hours.py`, que la tabla
#: `operating_hours` y que `datetime.weekday()` — a propósito: tres convenios distintos para el
#: mismo número es cómo se publica el estado del martes un lunes.
DAYS = 7

#: Techo de franjas por estado. No es un límite técnico: son dos publicaciones al día durante toda
#: la semana, y más que eso no es un horario, es un problema de volumen de salida disfrazado de
#: configuración.
MAX_SLOTS_PER_STATUS = 14


@dataclass(frozen=True)
class StatusSlot:
    """Una ocasión en la que un estado se publica.

    `minute` son minutos desde la medianoche en hora **local de la sede**, igual que
    `operating_hours`. Exactamente uno de `weekday` / `on_date` va puesto; la invariante se valida
    aquí y **además** vive como CHECK en la base, para que una inserción de un script no la rompa.
    """

    minute: int
    weekday: int | None = None
    on_date: date | None = None

    @property
    def is_dated(self) -> bool:
        return self.on_date is not None


@dataclass(frozen=True)
class DueSlot:
    """Una publicación que toca ahora (o que tocaba y llega tarde).

    `late_by` son los minutos transcurridos desde que venció. Se devuelve calculado porque es lo
    que el registro tiene que poder contar —"10:00 · omitido, 160 minutos tarde"— y calcularlo dos
    veces es cómo los dos sitios acaban discrepando.
    """

    minute: int
    late_by: int
    within_grace: bool


def validate_slots(slots: Sequence[StatusSlot]) -> None:
    """Valida el conjunto de franjas, o levanta `ValidationError` nombrando la culpable.

    Se valida **al guardar**, no al publicar. Un estado lo publica un worker a una hora programada
    sin nadie mirando: descubrir ahí que una franja era imposible significa que el dueño se entera
    por un teléfono vacío.
    """
    if len(slots) > MAX_SLOTS_PER_STATUS:
        raise ValidationError(
            f"Demasiadas franjas ({len(slots)}). El máximo es {MAX_SLOTS_PER_STATUS}."
        )

    for position, slot in enumerate(slots, start=1):
        where = f"Franja {position}"

        if (slot.weekday is None) == (slot.on_date is None):
            # Los dos o ninguno. El mensaje dice las dos formas válidas porque "franja inválida" a
            # secas no le dice a nadie qué arreglar.
            raise ValidationError(
                f"{where}: tiene que ser un día de la semana O una fecha concreta, no las dos "
                f"ni ninguna."
            )

        if not 0 <= slot.minute < MINUTES_PER_DAY:
            raise ValidationError(
                f"{where}: la hora está fuera del día (minuto {slot.minute})."
            )

        if slot.weekday is not None and not 0 <= slot.weekday < DAYS:
            raise ValidationError(
                f"{where}: día de la semana desconocido ({slot.weekday})."
            )

    _reject_duplicates(slots)


def _reject_duplicates(slots: Sequence[StatusSlot]) -> None:
    """Dos franjas idénticas son un error al guardar, no un duplicado que se limpia solo.

    Publicar sí las colapsaría —la clave de emisión es la misma— así que dejarlas pasar no rompería
    nada. Se rechazan igual: una lista con la misma hora dos veces es una pantalla que enseña algo
    que no va a pasar dos veces, y eso se arregla antes de guardar.
    """
    seen: set[tuple[int, int | None, date | None]] = set()
    for slot in slots:
        fingerprint = (slot.minute, slot.weekday, slot.on_date)
        if fingerprint in seen:
            raise ValidationError("Hay dos franjas con el mismo día y la misma hora.")
        seen.add(fingerprint)


def due_slots(
    slots: Iterable[StatusSlot],
    local_date: date,
    now_minute: int,
    grace_minutes: int,
) -> list[DueSlot]:
    """Las franjas que vencieron HOY, cada una con si llega dentro de la ventana de gracia.

    `local_date` es la fecha en la zona de la sede y **de ella sale el día de la semana**: no se
    recibe un `weekday` por separado porque dos parámetros para el mismo hecho pueden discrepar, y
    el modo de fallo de que discrepen es publicar el estado de otro día.

    Devuelve las dos clases juntas —a tiempo y tarde— en una sola pasada. Separarlas en dos
    funciones invita a que un camino se olvide de la gracia, que es exactamente el camino que
    vomita las publicaciones atrasadas de golpe tras un reinicio.

    **Colapsa por minuto.** Una franja de `weekday` y otra de `on_date` a la misma hora del mismo
    día son UNA publicación, no dos: la clave de emisión es `(estado, fecha, minuto)`, así que la
    segunda perdería el reclamo de todas formas. Colapsar aquí significa que lo que devuelve esta
    función es exactamente el conjunto de publicaciones que pueden ocurrir, y que quien llama no
    resuelve una audiencia para tirarla.

    Orden: por minuto ascendente. La de las once antes que la de las seis, que es como se lee
    un día.
    """
    weekday = local_date.weekday()

    due_minutes: set[int] = set()
    for slot in slots:
        matches_today = (
            slot.on_date == local_date
            if slot.is_dated
            else slot.weekday == weekday
        )
        if matches_today and slot.minute <= now_minute:
            due_minutes.add(slot.minute)

    return [
        DueSlot(
            minute=minute,
            late_by=now_minute - minute,
            within_grace=(now_minute - minute) <= grace_minutes,
        )
        for minute in sorted(due_minutes)
    ]


def emission_detail(status_id: uuid.UUID, local_date: date, minute: int) -> str:
    """`<id del estado>:<YYYY-MM-DD>:<minuto>` — la parte variable de la clave de emisión.

    **Esto no es la clave entera**, y la diferencia importa. La clave la compone
    `infrastructure/models.py:emission_key`, que es el único sitio donde se decide la forma de una
    clave de esa tabla ("cambiarla es cambiar qué cuenta como el mismo mensaje"), y este módulo no
    puede llamarla sin que el dominio dependa de la infraestructura. Así que aquí vive el trozo que
    merece ser puro y probado, y allí se le pone la clase delante:

        emission_key(EMISSION_STATUS_POST, detail=emission_detail(...))
        →  "status_post:8f3a…:2026-08-10:660"

    La clase es `status_post` y **no** `status` por un motivo concreto: `status` ya está tomada
    por los avisos de estado de un pedido (`status:<pedido>:<estado>`). Las dos clases nunca
    chocarían de verdad —un id de pedido no es un id de estado—, pero convivirían en la misma
    columna con la misma cara, y esa columna es justo donde se audita a mano por qué algo se envió
    dos veces.

    **Y no lleva el id de la franja.** Es lo menos obvio de todo el change, así que aquí queda el
    porqué entero. Las franjas se guardan borrando e reinsertando —como `operating_hours`, que es
    lo correcto para un conjunto que se edita entero—, luego cada guardado les da un UUID nuevo:

        11:00  se publica       →  emisión "...:<slot_A>:2026-08-09"
        11:05  el dueño corrige una tilde y guarda
               →  franjas borradas y reinsertadas: slot_A ya no existe, ahora es slot_Z
        11:06  el barrido busca "...:<slot_Z>:2026-08-09"  →  no hay  →  PUBLICA OTRA VEZ

    Un guardado inocuo dispara el reenvío, y el dueño no tiene forma de relacionar una cosa con la
    otra. La fecha y el minuto sobreviven a la reescritura, sirven igual para franjas semanales y de
    fecha concreta —la fecha local ya es el discriminante— y se leen en la base sin un solo join.

    Efecto secundario asumido: mover 11:00 → 11:30 el mismo día vuelve a publicar. Cambiaste la
    hora; querías que saliera a la nueva hora. Y quitar una franja no puede resucitar nada, porque
    lo que no existe no vence.
    """
    return f"{status_id}:{local_date.isoformat()}:{minute}"
