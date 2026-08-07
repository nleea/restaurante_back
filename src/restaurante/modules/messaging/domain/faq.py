"""FAQs por palabra clave: normalizar, comparar y elegir la primera que coincide.

Este es el **primer** mecanismo del módulo que lee lo que el cliente escribió, y eso obliga a
explicar por qué no contradice la regla #1 de `autoreply.py` ("nada de detectar intención… una
lista de palabras clave es una fábrica de bugs"). Esa regla habla del **saludo**: decidir la
PRIMERA respuesta por intención. El saludo sigue sin leer el texto. Lo que lee texto es esto, y
vive detrás de dos puertas que el saludo no tenía —conversación ya saludada y sin pedido vivo—,
más una tercera: contestar aquí **no cambia el estado de la conversación**, así que una
coincidencia equivocada es un mensaje bochornoso y no un cliente perdido.

Dos decisiones sostienen el fichero:

1. **Palabra o frase completa, nunca substring.** `pago` no puede encontrar "ya pagué y no me
   llegó", y `envian` no puede encontrar "¿ya me lo enviaron?". Esos dos son los falsos positivos
   con peor cara del conjunto y los mata el límite de palabra, no una lista más larga.
2. **Sin *stemming*.** Se prueba el singular y el plural del gatillo, y nada más. Recortar sufijos
   genéricos devolvería exactamente el bug del punto 1.

Funciones puras: sin base de datos, sin red, sin reloj. Mismo criterio que `templates.py`.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence

from restaurante.modules.messaging.domain.entities import FaqEntry
from restaurante.shared.customer_channel.vocabulary import (
    PERSON_WORDS,
    RESERVED_TRIGGER_WORDS,
)

_NON_ALNUM = re.compile(r"[^0-9a-z]+")

# Las vocales, para decidir si el plural de un gatillo lleva "s" o "es". No pretende ser
# gramática: pretende que `domicilio` encuentre `domicilios` sin que `pago` encuentre `pagué`.
_VOWELS = frozenset("aeiou")


def normalize(text: str) -> str:
    """Minúsculas, sin tildes, signos a espacio y espacios colapsados.

    Los DOS lados —gatillo y mensaje— reciben el mismo tratamiento, que es lo único que importa:
    `mañana` acaba en `manana` y da igual, porque el gatillo también. Buscar pureza lingüística
    aquí sería pagar por un problema que no existe.
    """
    lowered = unicodedata.normalize("NFD", text.lower())
    without_marks = "".join(c for c in lowered if not unicodedata.combining(c))
    return " ".join(_NON_ALNUM.sub(" ", without_marks).split())


def plural_variants(trigger: str) -> set[str]:
    """El gatillo normalizado, en singular y plural. Nunca recorta más que eso.

    `domicilio` → {domicilio, domicilios}. `horarios` → {horarios, horario}. Es lo que evita el
    precipicio de que un dueño escriba `domicilio` y el cliente escriba `domicilios`, sin abrir la
    puerta a que `pago` encuentre `pagué`.
    """
    base = normalize(trigger)
    if not base:
        return set()
    variants = {base}
    if len(base) > 3 and base.endswith("es"):
        variants.add(base[:-2])
    if len(base) > 2 and base.endswith("s"):
        variants.add(base[:-1])
    if not base.endswith("s"):
        variants.add(base + "s")
        if base[-1] not in _VOWELS:
            variants.add(base + "es")
    return variants


def matches(trigger: str, message: str) -> bool:
    """¿Aparece el gatillo en el mensaje como palabra o frase COMPLETA?

    El acolchado con espacios es lo que da el límite de palabra, y sirve igual para gatillos de
    varias palabras (`a que hora abren`) sin necesidad de una expresión regular por gatillo.
    """
    padded = f" {normalize(message)} "
    return any(f" {variant} " in padded for variant in plural_variants(trigger))


def matches_any(triggers: Iterable[str], message: str) -> bool:
    return any(matches(trigger, message) for trigger in triggers)


def first_match(faqs: Sequence[FaqEntry], message: str) -> FaqEntry | None:
    """La primera FAQ encendida cuyo gatillo coincida. El ORDEN de la lista es la prioridad.

    Se devuelve la primera y no "la mejor": el dueño tiene que poder mirar la lista y saber cuál
    va a ganar. Una regla de especificidad sería más fina y menos explicable, y la prioridad
    explícita se cuenta en cinco palabras.
    """
    for faq in faqs:
        if not faq.enabled or not faq.text.strip():
            continue
        if matches_any(faq.triggers, message):
            return faq
    return None


# Las palabras reservadas, ya normalizadas: la lista compartida trae `devolución` y `devolucion`
# porque el asistente compara sobre el texto en minúsculas, y aquí las dos son la misma.
_RESERVED = frozenset(
    normalized for normalized in map(normalize, RESERVED_TRIGGER_WORDS) if normalized
)
_PERSON = frozenset(
    normalized for normalized in map(normalize, PERSON_WORDS) if normalized
)


def reserved_words_in(trigger: str) -> list[str]:
    """Las palabras reservadas que CONTIENE este gatillo, para rechazarlo al guardar.

    Por contención y no por igualdad, y es lo fino de la validación: un gatillo `cancelaciones`
    no es igual a `cancelar`, así que pasaría una comprobación por igualdad — y luego no
    dispararía nunca, porque el mensaje que lo contiene contiene también `cancela` y
    `asks_for_a_person` lo manda a una persona antes de mirar FAQs. Una FAQ encendida que no
    puede coincidir es peor que una rechazada, porque nada la explica.
    """
    normalized = normalize(trigger)
    return sorted(word for word in _RESERVED if word in normalized)


def asks_for_a_person(message: str) -> bool:
    """¿Está pidiendo una persona, o cancelar/devolver? Entonces ninguna FAQ contesta.

    Subcadena, igual que el enrutado del asistente, y por eso `cancela` cubre "cancelación". El
    opt-in del asistente NO entra aquí: `1` como subcadena aparece en "quiero 1 hamburguesa" y en
    media calle de Riohacha, así que callaría a las FAQs casi siempre. Como gatillo sí está
    prohibido —ver `reserved_words_in`—, que es donde esa palabra hace daño.
    """
    normalized = normalize(message)
    return any(word in normalized for word in _PERSON)
