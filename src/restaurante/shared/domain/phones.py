"""Un teléfono escrito por una persona, comparable con uno que vino de WhatsApp.

Existe por un fallo que no da error: WhatsApp guarda el número tal y como sale del JID
—`573001112233`, sin `+`, sin espacios, sin guiones— y una persona lo escribe en la pantalla
de Personal como `+57 300 111 2233`. La comparación es texto contra texto, así que no coinciden,
el guardián rechaza el envío como "no contactable", lo anota en un log del servidor, y desde
fuera lo único que se ve es que el aviso nunca llegó.

La regla es una sola: **todo teléfono se normaliza antes de compararse o guardarse.**

Vive en `shared` y no en messaging porque lo necesitan los dos extremos del problema: quien
guarda el teléfono (Personal, que es identity/staff) y quien lo compara (messaging). Ponerlo
en uno de los dos obligaría al otro a importarlo, y "Personal depende de WhatsApp" es un
acoplamiento que no aguanta la siguiente pantalla que pida un teléfono.

Deliberadamente NO es una librería de números telefónicos. No valida prefijos de país, no sabe
qué es un móvil colombiano y no reformatea nada para mostrarlo. Sólo quita lo que la gente
escribe para leer mejor y que WhatsApp nunca puso.
"""

from __future__ import annotations

import re

_NON_DIGITS = re.compile(r"\D")


def normalize_phone(value: str) -> str:
    """`+57 (300) 111-2233` → `573001112233`.

    Se quedan sólo los dígitos. Es más agresivo que quitar una lista de símbolos, y a
    propósito: la lista de lo que la gente escribe para separar un número es infinita, y la
    de lo que WhatsApp guarda tiene un solo elemento.

    Un JID de privacidad (`123@lid`) se devuelve INTACTO: no es un teléfono, es lo único con
    lo que se le puede escribir a ese contacto, y quitarle el sufijo lo rompería. Ver
    `_phone_from_jid`.
    """
    trimmed = value.strip()
    if "@" in trimmed:
        return trimmed
    return _NON_DIGITS.sub("", trimmed)
