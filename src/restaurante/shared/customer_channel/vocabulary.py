"""Las palabras que ya tienen dueño en el canal del cliente.

Vive aquí y no en `assistant` porque **no son palabras del asistente**: son palabras que el canal
reserva, y ahora las necesitan dos módulos por dos motivos distintos.

- `assistant` las usa para **enrutar**: quién entra al bot, quién sale a una persona, y qué no lo
  resuelve ni el bot ni una vista.
- `messaging` las usa para **callar y para validar**: ninguna FAQ contesta un mensaje que pide una
  persona, y ningún gatillo de FAQ puede contener una de estas palabras — si lo contuviera, la FAQ
  quedaría encendida y sin poder coincidir nunca, que es la peor de las dos opciones.

Duplicarlas con un comentario habría sido el precedente de la casa para reglas espejadas **entre
capas** (el front espeja `templates.py` para no pedir una vista previa por tecla). Aquí las dos
copias vivirían del mismo lado de la misma frontera, así que derivarían sin que nada lo note.

Son datos, no un puerto: quien las usa decide cómo compara. `assistant` compara sobre el texto en
minúsculas —y por eso la lista trae las formas con y sin tilde—; `messaging` normaliza los dos
lados antes de comparar y las tildes le dan igual.
"""

from __future__ import annotations

# Cómo se entra al asistente. Coincidencia EXACTA sobre el mensaje entero: quien escribe "1"
# está aceptando la oferta del saludo, y quien escribe "necesito 1 hamburguesa" no.
OPT_IN_WORDS: frozenset[str] = frozenset({"1", "asistente", "bot"})

# Cómo se sale a una persona. Se comparan como SUBCADENA a propósito: "quiero hablar con alguien"
# y "hay alguien?" tienen que salir las dos, y el coste de un falso positivo aquí es mandar una
# conversación a la bandeja, que es donde acaba todo lo que no sabemos contestar.
HANDOFF_WORDS: tuple[str, ...] = (
    "humano",
    "persona",
    "asesor",
    "agente",
    "alguien",
    "operador",
)

# Lo que no resuelve ni el asistente ni ninguna vista: cancelar un pedido y devolver plata.
# También subcadena, y por eso "cancela" cubre "cancelación" y "cancelaciones".
REFUND_WORDS: tuple[str, ...] = (
    "cancelar",
    "cancela",
    "anular",
    "anula",
    "devolver",
    "devolución",
    "devolucion",
    "reembolso",
)

#: Lo que manda un mensaje a una persona, sea por petición o por materia.
PERSON_WORDS: tuple[str, ...] = HANDOFF_WORDS + REFUND_WORDS

#: Lo que no puede ser gatillo de una FAQ. Incluye el opt-in del asistente: un gatillo `1` jamás
#: dispararía, porque el opt-in se mira antes y gana.
RESERVED_TRIGGER_WORDS: tuple[str, ...] = tuple(sorted(OPT_IN_WORDS)) + PERSON_WORDS
