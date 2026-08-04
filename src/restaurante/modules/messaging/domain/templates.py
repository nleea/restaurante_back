"""Interpolación de marcadores para los mensajes automáticos.

Deliberadamente NO es un motor de plantillas. Un `{% if %}` en un texto que edita el dueño
de un restaurante es una forma de que la caja de texto pueda romper el envío, y nadie va a
depurar Jinja desde una pantalla de ajustes. Aquí sólo se sustituyen marcadores conocidos,
y los desconocidos se rechazan AL GUARDAR, no al enviar — un error a las 8pm frente a un
cliente esperando no sirve de nada.

Funciones puras: sin base de datos, sin red, sin reloj. Quien llama trae los valores.
"""

from __future__ import annotations

import re

# Los únicos marcadores que existen. Ampliar esta lista es una decisión de producto: cada
# uno es algo que el negocio puede poner en un mensaje y que nosotros garantizamos resolver.
PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "business_name",   # nombre del negocio, del Perfil del negocio
        "branch_name",     # nombre de la sede que recibió el mensaje
        "branch_address",  # dirección de esa sede
        "branch_phone",    # teléfono de esa sede
        "menu_link",       # enlace a la carta de ESA sede, con su token
        "next_opening",    # "mañana a las 8:00 a. m." — sólo si está cerrado
        "hours_line",      # "hoy hasta las 22:00" / "cerrados; abrimos mañana a las 8:00"
        "order_number",    # código corto del pedido
        "order_total",     # total formateado
        "order_items",     # el detalle de lo pedido, una línea por producto
    }
)

# La identidad del negocio (cómo se llama, dónde está, a qué número llamar) vale en CUALQUIER
# mensaje: un aviso de "pedido listo" que dice dónde recogerlo es mejor aviso.
IDENTITY_PLACEHOLDERS: frozenset[str] = frozenset(
    {"business_name", "branch_name", "branch_address", "branch_phone"}
)

# Marcadores que sólo existen en el saludo, y los que sólo existen en los avisos de pedido.
# Poner `{order_total}` en el saludo no es un error de sintaxis: es un texto que saldría con
# un hueco, y por eso se rechaza al guardar.
GREETING_PLACEHOLDERS: frozenset[str] = IDENTITY_PLACEHOLDERS | {
    "menu_link",
    "next_opening",
}
ORDER_PLACEHOLDERS: frozenset[str] = IDENTITY_PLACEHOLDERS | {
    "order_number",
    "order_total",
    "order_items",
}
# Las FAQs contestan una pregunta suelta, no un pedido: nada de `{order_*}` — un texto sobre "tu
# pedido" no tiene pedido del que hablar cuando lo dispara la palabra "horario".
#
# `{hours_line}` existe SÓLO aquí y es la razón por la que este conjunto no es el del saludo:
# `{next_opening}` salta por diseño las aperturas de hoy que ya pasaron, así que una FAQ de
# horario contestada a las 2 de la tarde diría "abrimos mañana a las 8:00" — cierto e inútil.
FAQ_PLACEHOLDERS: frozenset[str] = GREETING_PLACEHOLDERS | {"hours_line"}
# La tercera variante del saludo SÍ puede nombrar el pedido: existe precisamente porque hay uno
# esperando pago, y decir "tu pedido A3F2 por $46.000" es lo que le dice al agente —y al cliente—
# de qué se está hablando. Sin `{order_items}`: el saludo no es un catálogo.
AWAITING_PAYMENT_PLACEHOLDERS: frozenset[str] = GREETING_PLACEHOLDERS | {
    "order_number",
    "order_total",
}

_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")


def find_placeholders(text: str) -> set[str]:
    """Los marcadores que aparecen en el texto, sin juzgarlos."""
    return set(_PLACEHOLDER_RE.findall(text))


def unknown_placeholders(text: str, allowed: frozenset[str] = PLACEHOLDERS) -> set[str]:
    """Los que el texto usa y no existen — lo que hace fallar el guardado."""
    return find_placeholders(text) - allowed


def render(text: str, values: dict[str, str]) -> str:
    """Sustituye los marcadores presentes; deja intactos los que no tengan valor.

    Dejar `{next_opening}` visible cuando no hay dato es feo, pero es honesto y depurable.
    Sustituirlo por vacío produciría frases como "abrimos  " que nadie sabe de dónde salen.
    """

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = values.get(key)
        return value if value is not None else match.group(0)

    return _PLACEHOLDER_RE.sub(_replace, text)


# Nombres de día en español, para redactar la próxima apertura.
_WEEKDAYS = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)


def _clock(minute: int) -> str:
    """`1320` → `"22:00"`. Sin cero a la izquierda en la hora, como se lee en voz alta."""
    hour, minutes = divmod(minute, 60)
    return f"{hour}:{minutes:02d}"


def format_hours_line(
    closing: tuple[int, bool] | None, next_opening_label: str | None
) -> str | None:
    """El horario en una frase, correcta a cualquier hora. `None` cuando no hay horarios.

    Abierto → "hoy hasta las 22:00"; en una ventana que cruza la medianoche, "hasta las 2:00" sin
    el "hoy", que sería mentira a las once de la noche. Cerrado → "cerrados; abrimos mañana a las
    8:00".

    Existe porque `{next_opening}` no sirve para una FAQ de horario: contesta la mitad del día con
    la apertura de mañana. Y es un MARCADOR dentro de una frase que escribe el dueño, no una línea
    que el código pega al final — esa distinción es justo la queja que originó todo esto.
    """
    if closing is not None:
        minute, same_day = closing
        return f"hoy hasta las {_clock(minute)}" if same_day else f"hasta las {_clock(minute)}"
    if next_opening_label:
        return f"cerrados; abrimos {next_opening_label}"
    return None


def format_next_opening(
    opening: tuple[int, int] | None, today_weekday: int
) -> str | None:
    """"mañana a las 8:00", "el jueves a las 10:30". None cuando no hay horario.

    Se dice el día relativo cuando se puede ("hoy"/"mañana") porque es como habla la gente;
    para más lejos, el nombre del día, que es más útil que "en 4 días".
    """
    if opening is None:
        return None
    weekday, minute = opening
    clock = _clock(minute)
    delta = (weekday - today_weekday) % 7
    if delta == 0:
        return f"hoy a las {clock}"
    if delta == 1:
        return f"mañana a las {clock}"
    return f"el {_WEEKDAYS[weekday]} a las {clock}"
