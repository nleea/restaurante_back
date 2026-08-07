"""Acuses de entrega: traducir lo que dice el puente y decidir si el estado AVANZA.

Todo el fichero existe por una frase: **un acuse no puede retroceder.**

WhatsApp manda casi siempre dos acuses seguidos —entregado y leído— con milisegundos de
diferencia, y el puente los reenvía por HTTP con sus propios reintentos. O sea que llegan
desordenados con regularidad, no como caso raro. Aplicarlos a pelo hace que una palomita azul
parpadee a gris según el orden en que se resuelvan los reintentos, y **un acuse que retrocede es
peor que ningún acuse**: el agente ve "no leído" sobre algo que el cliente sí leyó, y llama por
teléfono a alguien que ya está atendido.

De ahí las dos piezas:

1. `advance` — la escala `pending < sent < delivered < read`, y sólo se sube.
2. `state_from_provider` — la traducción de los valores del puente, leída de su código
   (`evolution-api/src/utils/renderStatus.ts`), no de memoria.

`failed` está **fuera** de la escala a propósito: significa "no lo pudimos entregar al puente", y
un mensaje así nunca recibió un id de proveedor, así que ningún acuse puede emparejar con él. La
regla es una red, no un caso esperado.

Funciones puras: sin base de datos, sin red, sin reloj. Mismo criterio que `templates.py`.
"""

from __future__ import annotations

# La escala. `failed` NO está: no es un escalón, es el otro final.
#
# Que un estado no esté en el mapa significa "de aquí no se sale con un acuse", que es justo lo
# que se quiere de `failed`.
DELIVERY_RANK: dict[str, int] = {
    "pending": 0,
    "sent": 1,
    "delivered": 2,
    "read": 3,
}

# Lo que manda el puente, en `data.status`. Copiado de `renderStatus.ts`:
#   0 ERROR · 1 PENDING · 2 SERVER_ACK · 3 DELIVERY_ACK · 4 READ · 5 PLAYED
#
# Dos traducciones merecen explicación:
#
# - `PLAYED` (audio escuchado) cuenta como `read`. Un estado propio sería una palomita más que
#   explicar a cambio de una distinción que no le cambia ninguna decisión a un agente.
# - `ERROR` **no** se traduce a `failed`. Nuestro `failed` significa "el puente no lo aceptó", que
#   es accionable —se reenvía—; un `ERROR` posterior es otra cosa y no se sabe cuál, así que se
#   ignora en vez de inventarse un significado.
_PROVIDER_STATES: dict[str, str] = {
    "PENDING": "sent",
    # El puente manda `SERVER_ACK` también como valor por defecto cuando NO sabe el estado. Que
    # traduzca a `sent` lo vuelve inofensivo: el mensaje ya está ahí, `advance` no sube y no pasa
    # nada. Es exactamente el comportamiento que se quiere de un "no sé".
    "SERVER_ACK": "sent",
    "DELIVERY_ACK": "delivered",
    "READ": "read",
    "PLAYED": "read",
}


def state_from_provider(status: str) -> str | None:
    """El estado nuestro que corresponde a un `status` del puente, o `None` si no corresponde.

    `None` es "este acuse no dice nada que sepamos usar" —`ERROR`, o un valor que el puente añada
    en una versión futura— y quien llama lo trata como silencio, no como error.
    """
    return _PROVIDER_STATES.get(status.strip().upper())


def advance(current: str, incoming: str) -> str:
    """El estado resultante de aplicar `incoming` sobre `current`. Sólo sube.

    Devuelve `current` intacto cuando el acuse no aporta —llegó tarde, está repetido, o alguno de
    los dos está fuera de la escala—, así que quien llama puede comparar y saber si escribir.

    Saltarse un escalón SÍ vale: `sent` + `read` da `read`. Es lo que pasa de verdad cuando el
    cliente tiene el chat abierto y los dos acuses se funden en uno.
    """
    current_rank = DELIVERY_RANK.get(current)
    incoming_rank = DELIVERY_RANK.get(incoming)
    if current_rank is None or incoming_rank is None:
        # `current` fuera de la escala es `failed`: de ahí no se sale con un acuse.
        return current
    return incoming if incoming_rank > current_rank else current
